# Virtual Endpoints

The `bento_singularity` distribution provides several endpoints that are not
associated with a particular service, and are instead provided by Lua 
middleware within OpenResty. This document lists them and describes the
calling procedure and their function.



## Authentication

### `/api/auth/sign_in`

TODO


### `/api/auth/sign_out`

TODO


### `/api/auth/callback`

TODO



## User Information

### `/api/auth/user`

TODO



## One-Time Token Authorization

TODO: DESCRIPTION


### `/api/auth/ott/generate`

#### Request format:

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

```
DELETE
```

```json
{
  "token": "token1"
}
```

This request will return a `204` status code (with no content) if no server
error occurs, i.e. the token either didn't exist or was deleted. Either way, 
the end result is that the token supplied is invalid.


### `/api/auth/ott/invalidate_all`

This request is idempotent.

```
DELETE
```

This request takes no input, and will return a `204` status code (with no 
content) if no server error occurs, i.e. no tokens existed in the system, or 
all were deleted. Either way, the end result is that no token will be valid if 
passed.
