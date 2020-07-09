-- Script to manage authentication and some basic authorization for CHORD
-- services under an OpenResty (or similarly configured NGINX) instance.

local cjson = require("cjson")
local openidc = require("resty.openidc")

local uncached_response = function (status, mime, message)
  -- Helper method to return uncached responses directly from the proxy without
  -- needing an underlying service.
  ngx.status = status
  ngx.header["Content-Type"] = mime
  ngx.header["Cache-Control"] = "no-store"
  ngx.header["Pragma"] = "no-cache"  -- Backwards-compatibility for no-cache
  ngx.say(message)
  ngx.exit(status)
end

local OIDC_CALLBACK_PATH_NO_SLASH = "api/auth/callback"
local OIDC_CALLBACK_PATH = "/" .. OIDC_CALLBACK_PATH_NO_SLASH
local SIGN_IN_PATH = "/api/auth/sign-in"
local SIGN_OUT_PATH = "/api/auth/sign-out"
local USER_INFO_PATH = "/api/auth/user"

local auth_mode = function (private_uri)
  if ngx.var.uri and (ngx.var.uri == SIGN_IN_PATH or private_uri)
  then return nil     -- require authentication at the auth endpoint or in the private namespace
  else return "pass"  -- otherwise pass
  end
end

-- Load auth configuration for setting up lua-resty-oidconnect
local auth_file = assert(io.open(ngx.var.chord_auth_config))
local auth_params = cjson.decode(auth_file:read("*all"))
auth_file:close()

local config_file = assert(io.open(ngx.var.chord_instance_config))
local config_params = cjson.decode(config_file:read("*all"))
config_file:close()

-- Set defaults for any possibly-unspecified configuration options

local chord_debug = config_params["CHORD_DEBUG"]
if chord_debug == nil then
  chord_debug = false
end

local chord_permissions = config_params["CHORD_PERMISSIONS"]
if chord_permissions == nil then
  chord_permissions = true
end

local chord_private_mode = config_params["CHORD_PRIVATE_MODE"]
if chord_private_mode == nil then
  chord_private_mode = false
end

-- If in production, validate the SSL certificate if HTTPS is being used
local opts_ssl_verify = "no"
if not chord_debug then
  opts_ssl_verify = "yes"
end

-- If in production, enforce CHORD_URL as the base for redirect
local opts_redirect_uri = OIDC_CALLBACK_PATH
local opts_redirect_after_logout_uri = "/"
if not chord_debug then
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
  accept_none_alg = false,
  accept_unsupported_alg = false,
  ssl_verify = opts_ssl_verify,
}

-- Cache commonly-used ngx.var.uri to save expensive access call
local ngx_var_uri = ngx.var.uri or ""

-- Private URIs don't exist if the CHORD_PERMISSIONS flag is off (for dev)
-- All URIs are effectively "private" externally for CHORD_PRIVATE_MODE nodes
local is_private_uri = chord_permissions and (
  chord_private_mode or
  string.find(ngx_var_uri, "^/api/%a[%w-_]*/private")
)


-- Need to rewrite target URI for authenticate if we're in a sub-folder
local auth_target_uri = ngx.var.request_uri
if ngx_var_uri == OIDC_CALLBACK_PATH or auth_mode(is_private_uri) == nil then
  -- Going to attempt a redirect; possibly dealing with the OpenIDC callback
  local after_chord_url = ngx_var_uri:match("^/(.*)")
  if after_chord_url then
    -- If after_chord_url is not nil, i.e. ngx var uri starts with a /
    -- Re-assemble target URI with external URI prefixes/hosts/whatnot:
    auth_target_uri = config_params["CHORD_URL"] .. after_chord_url  .. "?" .. (ngx.var.args or "")
  end
end

local res, err, _, session = openidc.authenticate(opts, auth_target_uri, auth_mode(is_private_uri))
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
    uncached_response(ngx.HTTP_INTERNAL_SERVER_ERROR, "text/plain", err)
  end
end

-- If authenticate hasn't rejected us above but it's "open", i.e.
-- non-authenticated users can see the page, clear X-User and
-- X-User-Role by setting the value to nil.
local user_id
local user_role
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
    user_role = "user"
    for _, owner_id in ipairs(auth_params["OWNER_IDS"]) do
      -- Check each owner ID set in the auth params; if the current user's ID
      -- matches one, set the user's role to "owner".
      if owner_id == user_id then user_role = "owner" end
    end
    session.data.user_id = user_id
    session.data.user_role = user_role
    session:save()
  end
elseif session ~= nil then
  -- Close the session, since we don't need it anymore
  session:close()
end

if is_private_uri and user_role ~= "owner" then
  -- TODO: Check ownership / grants?
  uncached_response(ngx.HTTP_FORBIDDEN, "text/plain", "Forbidden")
end

-- Clear and possibly set internal headers to inform services of user identity
-- and their basic role/permissions set (either the node's owner or a user of
-- another type.)
-- TODO: Pull this from session for performance
ngx.req.set_header("X-User", user_id)
ngx.req.set_header("X-User-Role", user_role)

-- Endpoint: /api/auth/user
--   Generates a JSON response with user data if the user is authenticated;
--   otherwise returns a 403 Forbidden error.
if ngx_var_uri == USER_INFO_PATH then
  if res == nil then
    uncached_response(ngx.HTTP_FORBIDDEN, "text/plain", "Forbidden")
  else
    res.user["chord_user_role"] = user_role
    uncached_response(ngx.HTTP_OK, "application/json", cjson.encode(res.user))
  end
end

-- Endpoint: /api/auth/sign-in
--   - If the user has not signed in, this will get caught above by the
--     authenticate() call;
--   - If the user just signed in and was redirected here, check the args for
--     a redirect parameter and return a redirect if necessary.
-- TODO: Do the same for sign-out (in certain cases)
if ngx_var_uri == SIGN_IN_PATH then
  local args, args_error = ngx.req.get_uri_args()
  if args_error == nil then
    local redirect = args.redirect
    if redirect and type(redirect) ~= "table" then
      ngx.redirect(redirect)
    end
  end
end
