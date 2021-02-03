-- Script to manage authentication and some basic authorization for CHORD
-- services under an OpenResty (or similarly configured NGINX) instance.

-- Note: Many things are cached locally; this is considered good practice in
--       the context of OpenResty given that non-local variable access is quite
--       slow. This includes ngx, require, table accesses, etc.

local ngx = ngx
local require = require

local cjson = require("cjson")
local openidc = require("resty.openidc")
local random = require("resty.random")
local redis = require("resty.redis")

local uncached_response = function (status, mime, message)
  -- Helper method to return uncached responses directly from the proxy without
  -- needing an underlying service.
  ngx.status = status
  if mime then ngx.header["Content-Type"] = mime end
  ngx.header["Cache-Control"] = "no-store"
  ngx.header["Pragma"] = "no-cache"  -- Backwards-compatibility for no-cache
  if message then ngx.say(message) end
  ngx.exit(status)
end

local OIDC_CALLBACK_PATH = "/api/auth/callback"
local OIDC_CALLBACK_PATH_NO_SLASH = OIDC_CALLBACK_PATH:sub(2, #OIDC_CALLBACK_PATH)
local SIGN_IN_PATH = "/api/auth/sign-in"
local SIGN_OUT_PATH = "/api/auth/sign-out"
local USER_INFO_PATH = "/api/auth/user"

local ONE_TIME_TOKENS_GENERATE_PATH = "/api/auth/ott/generate"
local ONE_TIME_TOKENS_CLEAR_ALL_PATH = "/api/auth/ott/clear_all"

local REDIS_SOCKET = "unix:/chord/tmp/redis.sock"

-- Create an un-connected Redis object
local red_ok
local red, red_err = redis:new()
if red_err then
  uncached_response(
    ngx.HTTP_INTERNAL_SERVER_ERROR,
    "application/json",
    cjson.encode({message=red_err, tag="ott redis conn", user_role=nil}))
end

-- Load auth configuration for setting up lua-resty-oidconnect
local auth_file = assert(io.open(ngx.var.chord_auth_config))
local auth_params = cjson.decode(auth_file:read("*all"))
auth_file:close()

local config_file = assert(io.open(ngx.var.chord_instance_config))
local config_params = cjson.decode(config_file:read("*all"))
config_file:close()

local auth__owner_ids = auth_params["OWNER_IDS"]
if auth__owner_ids == nil then
  auth__owner_ids = {}
end

-- TODO: This should probably be procedural instead of a function?
local get_user_role = function (user_id)
  user_role = "user"
  for _, owner_id in ipairs(auth__owner_ids) do
    -- Check each owner ID set in the auth params; if the current user's ID
    -- matches one, set the user's role to "owner".
    if owner_id == user_id then user_role = "owner" end
  end
  return user_role
end

-- Set defaults for any possibly-unspecified configuration options, including
-- some boolean casts

local CHORD_DEBUG = not (not config_params["CHORD_DEBUG"])

-- Cannot use "or" shortcut, otherwise would always be true
local CHORD_PERMISSIONS = config_params["CHORD_PERMISSIONS"]
if CHORD_PERMISSIONS == nil then CHORD_PERMISSIONS = true end

local CHORD_PRIVATE_MODE = not (not config_params["CHORD_PRIVATE_MODE"])

-- If in production, validate the SSL certificate if HTTPS is being used (for
-- non-Lua folks, this is a ternary - ssl_verify = !chord_debug)
local opts_ssl_verify = CHORD_DEBUG and "no" or "yes"

-- If in production, enforce CHORD_URL as the base for redirect
local opts_redirect_uri = OIDC_CALLBACK_PATH
local opts_redirect_after_logout_uri = "/"
if not CHORD_DEBUG then
  opts_redirect_uri = config_params["CHORD_URL"] .. OIDC_CALLBACK_PATH_NO_SLASH
  opts_redirect_after_logout_uri = config_params["CHORD_URL"]
end

local opts = {
  redirect_uri = opts_redirect_uri,
  logout_path = SIGN_OUT_PATH,
  redirect_after_logout_uri = opts_redirect_after_logout_uri,

  discovery = auth_params["OIDC_DISCOVERY_URI"],

  client_id = auth_params["CLIENT_ID"],
  client_secret = auth_params["CLIENT_SECRET"],

  -- Default token_endpoint_auth_method to client_secret_basic
  token_endpoint_auth_method = auth_params["TOKEN_ENDPOINT_AUTH_METHOD"] or "client_secret_basic",

  accept_none_alg = false,
  accept_unsupported_alg = false,
  ssl_verify = opts_ssl_verify,

  -- Disable keepalive to try to prevent some "lost access token" issues with the OP
  -- See https://github.com/zmartzone/lua-resty-openidc/pull/307 for details
  keepalive = "no",

  -- TODO: Re-enable this if it doesn't cause sign-out bugs, since it's more secure
  -- refresh_session_interval = 600,
  iat_slack = 120,
}

-- Cache commonly-used ngx.var.uri and ngx.var.request_method to save expensive access calls
local URI = ngx.var.uri or ""
local REQUEST_METHOD = ngx.var.request_method or "GET"

-- Track if the current request is to an API
local is_api_uri = string.find(URI, "^/api")

-- Private URIs don't exist if the CHORD_PERMISSIONS flag is off (for dev)
-- All URIs are effectively "private" externally for CHORD_PRIVATE_MODE nodes
local is_private_uri = CHORD_PERMISSIONS and (
  (CHORD_PRIVATE_MODE and not string.find(URI, "^/api/auth")) or
  string.find(URI, "^/api/%a[%w-_]*/private")
)


-- Calculate auth_mode for authenticate() calls,
-- defining the redirect/return behaviour for the OIDC library
--  - "pass" --> keep going, but not with any auth headers set
--  - "deny" --> return 401
--  - nil    --> return 302 to sign-in page
--           --> always the case if the path requested is SIGN_IN
local auth_mode
if URI and URI ~= SIGN_IN_PATH then
  if is_private_uri then
    -- require authentication at the auth endpoint or in the private namespace
    -- (or if we're in private mode)
    if is_api_uri then
      -- We don't want to return any 302 redirects if we're accessing an
      -- endpoint that needs re-authorization, so deny in this case
      auth_mode = "deny"
    end
    -- else: If we're not authenticated, redirect to the OP (leave as nil)
  else
    auth_mode = "pass"  -- otherwise pass
  end
end


-- Need to rewrite target URI for authenticate if we're in a sub-folder
local auth_target_uri = ngx.var.request_uri
if URI == OIDC_CALLBACK_PATH or auth_mode == nil then
  -- Going to attempt a redirect; possibly dealing with the OpenIDC callback
  local after_chord_url = URI:match("^/(.*)")
  if after_chord_url then
    -- If after_chord_url is not nil, i.e. ngx var uri starts with a /
    -- Re-assemble target URI with external URI prefixes/hosts/whatnot:
    auth_target_uri = config_params["CHORD_URL"] .. after_chord_url  .. "?" .. (ngx.var.args or "")
  end
end

local user
local user_id
local user_role
local nested_auth_header

local err_user_not_owner = cjson.encode({message="Forbidden", tag="user not owner", user_role=user_role})
local err_user_nil = cjson.encode({message="Forbidden", tag="user is nil", user_role=user_role})

local req_headers = ngx.req.get_headers()

-- TODO: OTT headers are technically also a Bearer token (of a different nature)... should be combined
local ott_header = req_headers["X-OTT"]
if ott_header and URI ~= ONE_TIME_TOKENS_GENERATE_PATH and URI ~= ONE_TIME_TOKENS_CLEAR_ALL_PATH then
  -- Cannot use a one-time token to bootstrap generation of more one-time
  -- tokens or invalidate existing ones
  -- URIs do not include URL parameters, so this is safe from non-exact matches

  red_ok, red_err = red:connect(REDIS_SOCKET)
  if red_err then  -- Error occurred while connecting to Redis
    uncached_response(ngx.HTTP_INTERNAL_SERVER_ERROR, "application/json",
      {message=red_err, tag="redis conn", user_role=nil})
  end
  if type(ott_header) ~= "string" then
    uncached_response(ngx.HTTP_BAD_REQUEST, "application/json",
      {message="Bad one-time token header", tag="ott header bad", user_role=nil})
  end

  -- TODO: Error handling for each command? Maybe overkill

  -- Fetch all token data from the Redis store and subsequently delete it
  red:init_pipeline(10)
  local expiry = red:hmget("bento_ott:expiry", ott_header)
  local scope = red:hmget("bento_ott:scope", ott_header)
  user = cjson.decode(red:hmget("bento_ott:user", ott_header) or "null")
  user_id = red:hmget("bento_ott:user_id", ott_header)
  user_role = red:hmget("bento_ott:user_role", ott_header)
  red:hdel("bento_ott:expiry", ott_header)
  red:hdel("bento_ott:scope", ott_header)
  red:hdel("bento_ott:user_id", ott_header)
  red:hdel("bento_ott:user_role", ott_header)
  red:commit_pipeline()

  -- Update NGINX time (which is cached)
  ngx.update_time()

  -- Check token validity
  if expiry == nil then
    -- Token cannot be found in the Redis store
    uncached_response(ngx.HTTP_FORBIDDEN, "application/json",
      {message="Invalid one-time token", tag="ott invalid", user_role=nil})
  elseif expiry < ngx.time() then
    -- Token expiry date is in the past, so it is no longer valid
    uncached_response(ngx.HTTP_FORBIDDEN, "application/json",
      {message="Expired one-time token", tag="ott expired", user_role=nil})
  elseif URI:sub(1, #scope) ~= scope then
    -- Invalid call made with the token (out of scope)
    -- We're harsh here and still delete the token out of security concerns
    uncached_response(ngx.HTTP_FORBIDDEN, "application/json",
      {message="Out-of-scope one-time token", tag="ott out of scope", user_role=nil})
  end

  -- No nested auth header is set; OTTs cannot be used to bootstrap a full bearer token

  -- Put Redis connection into a keepalive pool for 30 seconds
  red_ok, red_err = red:set_keepalive(30000, 100)
  if red_err then
    uncached_response(ngx.HTTP_INTERNAL_SERVER_ERROR, "application/json",
      {message=red_err, tag="redis keepalive failed", user_role=user_role})
  end
else
  -- Check bearer token if set
  -- Adapted from https://github.com/zmartzone/lua-resty-openidc/issues/266#issuecomment-542771402
  local auth_header = ngx.req.get_headers()["Authorization"]
  if is_private_uri and auth_header and string.find(auth_header, "^Bearer .+") then
    -- A Bearer auth header is set, use it instead of session through introspection
    local res, err = openidc.introspect(opts)
    if err == nil and res.active then
      -- If we have a valid access token, try to get the user info
      --   - Slice out the token from the Authorization header
      user, err = openidc.call_userinfo_endpoint(
        opts, auth_header:sub(auth_header:find(" ") + 1))
      if err == nil then
        -- User profile fetch was successful, grab the values
        user_id = user.sub
        user_role = get_user_role(user_id)
        nested_auth_header = auth_header
      end
    end

    -- Log any errors that occurred above
    if err then ngx.log(ngx.ERR, err) end
  else
    -- If no Bearer token is set, use session cookie to get authentication information
    local res, err, _, session = openidc.authenticate(
      opts, auth_target_uri, auth_mode)
    if res == nil or err then  -- Authentication wasn't successful
      -- Authentication wasn't successful; clear the session and
      -- re-attempting (for a maximum of 2 times.)
      if session ~= nil then
        if session.data.user_id ~= nil then
          -- Destroy the current session if it exists and just expired
          session:destroy()
        elseif err then
          -- Close the current session before returning an error message
          session:close()
        end
      end
      if err then
        uncached_response(
          ngx.HTTP_INTERNAL_SERVER_ERROR,
          "application/json",
          cjson.encode({message=err, tag="no bearer, authenticate", user_role=nil})
        )
      end
    end

    -- If authenticate hasn't rejected us above but it's "open", i.e.
    -- non-authenticated users can see the page, clear X-User and
    -- X-User-Role by setting the value to nil.
    if res ~= nil then  -- Authentication worked
      if session.data.user_id ~= nil then
        -- Load user_id and user_role from session if available
        user_id = session.data.user_id
        user_role = session.data.user_role
        -- Close the session, since we're done loading data from it
        session:close()
      else
        -- Save user_id and user_role into session for future use
        user_id = res.id_token.sub
        user_role = get_user_role(user_id)
        session.data.user_id = user_id
        session.data.user_role = user_role
        session:save()
      end

      -- Set user object for possible /api/auth/user response
      user = res.user

      -- Set Bearer header for nested requests
      --  - First tries to use session-derived access token; if it's unset,
      --    try using the response access token.
      -- TODO: Maybe only res token needed?
      local auth_token = res.access_token
      if auth_token == nil then
        auth_token, err = openidc.access_token()  -- TODO: Remove this block?
        if err ~= nil then ngx.log(ngx.ERR, err) end
      end
      if auth_token ~= nil then
        nested_auth_header = "Bearer " .. auth_token
      end
    elseif session ~= nil then
      -- Close the session, since we don't need it anymore
      session:close()
    end
  end
end
-- Either authenticated or not, so from hereon out we:
--  - Handle scripted virtual endpoints (user info, sign in, OTT stuff)
--  - Check access given the URL
--  - Set proxy-internal headers

if URI == USER_INFO_PATH then
  -- Endpoint: /api/auth/user
  --   Generates a JSON response with user data if the user is authenticated;
  --   otherwise returns a 403 Forbidden error.
  if user == nil then
    uncached_response(
      ngx.HTTP_FORBIDDEN,
      "application/json",
      cjson.encode({message="Forbidden", tag="user nil", user_role=nil}))
  else
    user["chord_user_role"] = user_role
    uncached_response(ngx.HTTP_OK, "application/json", cjson.encode(user))
  end
elseif URI == SIGN_IN_PATH then
  -- Endpoint: /api/auth/sign-in
  --   - If the user has not signed in, this will get caught above by the
  --     authenticate() call;
  --   - If the user just signed in and was redirected here, check the args for
  --     a redirect parameter and return a redirect if necessary.
  -- TODO: Do the same for sign-out (in certain cases)
  local args, args_error = ngx.req.get_uri_args()
  if args_error == nil then
    local redirect = args.redirect
    if redirect and type(redirect) ~= "table" then
      ngx.redirect(redirect)
    end
  end
elseif REQUEST_METHOD == "POST" and URI == ONE_TIME_TOKENS_GENERATE_PATH then
  if user_role == nil then
    uncached_response(ngx.HTTP_FORBIDDEN, "application/json", err_user_nil)
  end

  local req_body = cjson.decode(ngx.request.body or "null")
  if type(req_body) ~= "table" then
    uncached_response(ngx.HTTP_BAD_REQUEST, "application/json",
      cjson.encode({message="Missing or invalid body", tag="invalid body", user_role=user_role}))
  end

  local scope = req_body["scope"]
  if not scope or type(scope) ~= "string" then
    uncached_response(ngx.HTTP_BAD_REQUEST, "application/json",
      cjson.encode({message="Missing or invalid token scope", tag="invalid scope", user_role=user_role}))
  end

  red_ok, red_err = red:connect(REDIS_SOCKET)
  if red_err then
    uncached_response(ngx.HTTP_INTERNAL_SERVER_ERROR, "application/json",
      {message=red_err, tag="redis conn", user_role=user_role})
  end

  -- Update NGINX internal time cache
  ngx.update_time()

  local new_token
  local new_tokens = {}
  local n_tokens = math.max(req_body["number"] or 1, 1)

  -- Generate n_tokens new tokens
  red:init_pipeline(5 * n_tokens)
  for _ = 1, n_tokens do
    -- Generate a new token (using OpenSSL via lua-resty-random), 128 characters long
    -- Does not use the token method, since that does not use OpenSSL
    new_token = random.bytes(64, "hex")
    table.insert(new_tokens, new_token)
    red:hset("bento_ott:expiry", new_token, ngx.time() + 10080)  -- Set expiry to current time + 7 days
    red:hset("bento_ott:scope", new_token, scope)
    red:hset("bento_ott:user", new_token, cjson.encode(user))
    red:hset("bento_ott:user_id", new_token, user_id)
    red:hset("bento_ott:user_role", new_token, user_role)
  end
  red:commit_pipeline()

  -- Put Redis connection into a keepalive pool for 30 seconds
  red_ok, red_err = red:set_keepalive(30000, 100)
  if red_err then
    uncached_response(ngx.HTTP_INTERNAL_SERVER_ERROR, "application/json",
      cjson.encode({message=red_err, tag="redis keepalive failed", user_role=user_role}))
  end

  -- Return the newly-generated tokens to the requester
  uncached_response(ngx.HTTP_OK, "application/json", cjson.encode(new_tokens))
elseif REQUEST_METHOD == "POST" and URI == ONE_TIME_TOKENS_CLEAR_ALL_PATH then
  if user_role ~= "owner" then
    uncached_response(ngx.HTTP_FORBIDDEN, "application/json", err_user_not_owner)
  end

  red_ok, red_err = red:connect(REDIS_SOCKET)
  if red_err then
    uncached_response(ngx.HTTP_INTERNAL_SERVER_ERROR, "application/json",
      {message=red_err, tag="redis conn", user_role=user_role})
  end

  red:init_pipeline(5)
  red:del("bento_ott:expiry")
  red:del("bento_ott:scope")
  red:del("bento_ott:user")
  red:del("bento_ott:user_id")
  red:del("bento_ott:user_role")
  red:commit_pipeline()

  -- Put Redis connection into a keepalive pool for 30 seconds
  red_ok, red_err = red:set_keepalive(30000, 100)
  if red_err then
    uncached_response(ngx.HTTP_INTERNAL_SERVER_ERROR, "application/json",
      {message=red_err, tag="redis keepalive failed", user_role=user_role})
  end
elseif is_private_uri and user_role ~= "owner" then
  -- Check owner status before allowing through the proxy
  -- TODO: Check ownership / grants?
  uncached_response(ngx.HTTP_FORBIDDEN, "application/json", err_user_not_owner)
end

-- Clear and possibly set internal headers to inform services of user identity
-- and their basic role/permissions set (either the node's owner or a user of
-- another type.)
-- Set an X-Authorization header containing a valid Bearer token for nested
-- requests to other services.
-- TODO: Pull this from session for performance
ngx.req.set_header("X-User", user_id)
ngx.req.set_header("X-User-Role", user_role)
ngx.req.set_header("X-Authorization", nested_auth_header)
