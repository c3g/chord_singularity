# Virtual Endpoints

The `bento_singularity` distribution provides several endpoints that are not
associated with a particular service, and are instead provided by Lua 
middleware within OpenResty. This document lists them and describes the
calling procedure and their function.



## Authentication

### `/api/auth/sign_in`

**Note:** This should probably be moved to outside the `/api` URL space in the
future, since it is not an API call per se.

Redirects the user to the OIDC Provider (OP) for sign in. Upon success, the 
user will be redirected back to the OIDC callback endpoint (see below.)

Any request type (`GET`, `POST`, ...) will get a redirect here.


### `/api/auth/sign_out`

**Note:** This should probably be moved to outside the `/api` URL space in the
future, since it is not an API call per se.

Signs the user out of the instance and redirects back to the homepage.


### `/api/auth/callback`

The OIDC authentication callback endpoint. This should not be pointed at by 
anything, as it is handled automatically by the `lua-resty-openidc` plugin.



## User Information

### `/api/auth/user`

```GET```

Returns information about the signed-in user, including the role within the
current Bento instance and any information fetched from the OP, in JSON format.

#### Response format

```json
{
  "chord_user_role": "owner",
  "email_verified": false,
  "sub": "...",
  "preferred_username": "admin"
}
```

`sub` is the subject ID within the OP, and is used to assign `chord_user_role`.



## One-Time Token Authorization

There are some circumstances where services need to make requests well after
the request which triggered it has been made, meaning the access token passed
is expired. In this case, one needs a mechanism for services to make (possibly 
federated / non-local) requests. For this purpose, a system of one-time-use 
tokens was implemented which can, within a specific URL scope, make a 
single request to perform an action.

These tokens are securely generated using a wrapper over OpenSSL and cached in
a Redis store on the instance. They have an expiry of 604800 seconds (= 7 days) 
from the time of creation.


### `/api/auth/ott/generate`

#### Request format

```POST```

```json
{
  "scope": "/api/my_service/",
  "number": 1
}
```

The `scope` parameter must end in a slash, and must not be in the 
`/api/auth/` URL space.

The `number` parameter must be at least 1 and at most 30.

#### Response format

This request will return a JSON list of generated one-time use tokens, which
can be used as described above:

```json
[
  "token1",
  "token2",
  "..."
]
```


### `/api/auth/ott/invalidate`

This request is idempotent.

#### Request format

```
DELETE
```

```json
{
  "token": "token1"
}
```

#### Response format

The above request will return a `204` status code (with no content) if no 
server error occurs, i.e. the token either didn't exist or was deleted. Either 
way, the end result is that the token supplied is invalid.


### `/api/auth/ott/invalidate_all`

This request is idempotent.

```
DELETE
```

This request takes no input, and will return a `204` status code (with no 
content) if no server error occurs, i.e. no tokens existed in the system, or 
all were deleted. Either way, the end result is that no token will be valid if 
passed.
