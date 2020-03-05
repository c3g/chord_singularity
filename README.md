# CHORD Singularity

![Build Status](https://travis-ci.org/c3g/chord_singularity.svg?branch=master)

What's included in a CHORD Singularity container?

  * NodeJS 12
  * Python 3.7
  * Java 11
  * A Redis instance running at `/chord/tmp/redis.sock`
  * A PostgreSQL 11 instance running at `/chord/tmp/postgresql/.s.PGSQL.5433`,
    with a username stored in the environment variable `POSTGRES_USER` and a
    service-specific database stored in the environment variable
    `POSTGRES_DATABASE`
  * `zlib1g-dev`, `libbz2-dev`, and `liblzma-dev`
  * `htslib`

**Note:** Google DNS servers are used to resolve OIDC IdP domain names.


## Setting Up the Build/Development Environment

### Setup

## Developing and Building

### Setting Up the Build/Development Environment

#### 1. Singularity

To install Singularity, follow the
[Singularity installation guide](https://sylabs.io/guides/3.5/user-guide/quick_start.html).

CHORD requires **Singularity 3.5** (or later compatible versions.)

#### 2. (Optional) Virtual Environment

Although the `dev_utils.py` script doesn't need any external dependencies, it
may be useful to create a virtual environment with a specific version of Python
3.6 (or higher) when developing:

```bash
virtualenv -p python3 ./env
source env/bin/activate
```

#### 3. Reverse Proxy

NGINX can be set up as a reverse proxy outside of the containers to create a
development CHORD cluster.

##### Example Development NGINX Configuration

Configuration for a **development** CHORD cluster, to use with `dev_utils.py`:

```nginx
server {
    listen 80;

    server_name ~^(\d+)\.chord\.dlougheed\.com$;

    location / {
        # Tweak these as needed for the security concerns of the instance.
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' '*' always;
        add_header 'Access-Control-Allow-Headers' '*' always;

        try_files $uri @container;
    }

    location @container {
        proxy_pass                       http://unix:/tmp/chord/$1/nginx.sock;
        proxy_buffer_size                128k;
        proxy_buffers                    4 256k;
        proxy_busy_buffers_size          256k;
        proxy_http_version               1.1;
        proxy_set_header Host            $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header Upgrade         $http_upgrade;
        proxy_set_header Connection      "upgrade";
    }
}
```

This configuration assumes that `*.chord.dlougheed.com` (in this example) has
a DNS record set up to point at 127.0.0.1.

**Note:** This NGINX configuration is unsuitable for production, since it
has a wide-open CORS policy allowing requests from anywhere.


### Building

**Building only works on Linux-based operating systems.**

To build the image:

```bash
./dev_utils.py build
```

You will be asked for your password by Singularity.


### Setting Up Authentication

CHORD uses OpenID Connect (OIDC) to authenticate users. With the **development
cluster**, instances' OIDC configurations can be specified in
`instance_auth.json`.

The easiest way to get a development OIDC Identity Provider (IdP) is to install
[Keycloak](https://www.keycloak.org/docs/latest/getting_started/index.html) and
run the standalone server provided.

After installing Keycloak, clients supporting the authorization code OIDC
workflow can be set up, and configuration copied over to `instance_auth.json`.

Setting up a fresh Keycloak installation to accomplish this entails:

  * Creating a new client (`chord1` is the default for the first node)
  * Specifying a root URL (e.g. `http://1.chord.dlougheed.com/`)
  * Setting this client's access type as "confidential"
    (this will let you access the "Credentials" tab and the
    secret needed for `instance_auth.json`)

See [Configuring an Instance](#configuring-an-instance) for descriptions of
what configuration values are available for each node in `instance_auth.json`.


### Running a Development Cluster

Assumes `/tmp/chord` and `~/chord_data` are writable directories.

**Note:** CHORD temporary and data directories can be specified by editing
`dev_utils.py` (not recommended) or setting `CHORD_DATA_DIRECTORY` and
`CHORD_TEMP_DIRECTORY` when running `dev_utils.py`.

To run a development cluster with `n` nodes, where `n` is some positive integer:

```bash
./dev_utils.py --cluster n start
```

Other available actions for `./dev_utils.py` are `stop` and `restart`.


### Bind Locations

`CHORD_DATA_DIRECTORY`: `/chord/data`
* Stores persistent data including databases and data files

`CHORD_TEMP_DIRECTORY`: `/chord/tmp`
* Stores boot-lifecycle (i.e. shouldn't be removed while CHORD is running, but
  may be removed when shut down) files including UNIX sockets and log files



## Configuring an Instance

Some files are needed in the CHORD `data` folder to configure the node.

**These files are automatically created when using the `dev_utils.py` script,
but should be set up in another way for production deployment.**

Values for each node's `.auth_config.json` are populated from the
[`instance_auth.json`](instance_auth.json) file at instance start time when
using `dev_utils.py`.

  * `.instance_config.json`, containing the following key-value pairs:
    * `CHORD_DEBUG` (`boolean`): Whether the container is started in debug
      mode. **Important security note:** debug mode is **insecure** and cannot
      be used in production **AT ALL**.
    * `CHORD_PERMISSIONS` (`boolean`): Whether the container, and services
      within, use the default CHORD permissions system. Turning this off
      WITHOUT an alternative in place is **insecure** and **cannot** be used in
      production **AT ALL**.
    * `CHORD_HOST` (`string`): The domain name of the host (no `http://`, no
      trailing slash, no sub-paths)
    * `CHORD_URL` (`string`): The URL of the node (for federation), including
      trailing slash, and sub path (if any)
    * `CHORD_REGISTRY_URL` (`string`): The URL of the registry node (for
      federation), with trailing slash, and sub path (if any.) A
      **registry node** is a trusted CHORD node which is the de-facto reference
      for the peer list.
  * `.auth_config.json`:
    * `OIDC_DISCOVERY_URI` (`string`): The discovery URI (typically
      `.../.well_known/openid-configuration`) for the OIDC IdP
    * `CLIENT_ID` (`string`): The client ID for the node in the OIDC IdP
    * `CLIENT_SECRET` (`string`): The client secret for the node in the OIDC
       IdP
    * `OWNER_IDS` (`array` of `string`): The subject IDs (from the OIDC IdP) of
       the node's owner(s)

Example configuration files are available in the
[`example_config/`](https://github.com/c3g/chord_singularity/tree/master/example_config)
folder.

**If in production:** Everything should be ran with SSL enabled; both
`OIDC_DISCOVERY_URI` and the site itself should be configured to use `https`.


### Example Production NGINX Configuration

TODO: Figure out if WSS works here

```nginx
server {
    listen 80;
    server_name chord.example.org;
    server_tokens off;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;

    # Insert production SSL configuration here
    ssl_certificate     chord.example.org.crt;
    ssl_certificate_key chord.example.org.key;

    server_name chord.example.org;
    server_tokens off;

    location / {
        try_files $uri @container;
    }

    location ~ ^\/api\/(?!auth) {
        # Tweak these as needed for the security concerns of the instance.
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' '*' always;
        add_header 'Access-Control-Allow-Headers' '*' always;

        try_files $uri @container;
    }

    location @container {
        proxy_pass                       http://unix:/tmp/chord/nginx.sock;
        proxy_buffer_size                128k;
        proxy_buffers                    4 256k;
        proxy_busy_buffers_size          256k;
        proxy_http_version               1.1;
        proxy_set_header Host            $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header Upgrade         $http_upgrade;
        proxy_set_header Connection      "upgrade";
    }
}
```



## Running an Instance

### Running as a Singularity Instance

The following command will start an instance as `chord1`, assuming
`.auth_config.json` and `.instance_config.json` have been created by hand in
the `CHORD_DATA_DIRECTORY` location:

```bash
singularity instance start \
	--bind /path/to/chord_tmp:/chord/tmp \
	--bind /path/to/chord_data:/chord/data \
	--bind /usr/share/zoneinfo/Etc/UTC:/usr/share/zoneinfo/Etc/UTC \
	/path/to/chord.sif \
	chord1
```

**Note:** In some cases timezone issues were encountered in the Singularity
image build; binding the UTC definition from the host is a hack-y fix for this.


#### Stopping the Instance

An extra step must be taken to stop the new `chord1` instance safely - a stop
script was written to facilitate this:

```bash
singularity exec instance://chord1 bash /chord/container_scripts/stop_script.bash
singularity instance stop chord1
```


### Running in Docker

**Note:** Docker support is experimental and possibly insecure. Use Singularity
when possible. Proper Docker support is planned for a later release.

`.auth_config.json` and `.instance_config.json` will need to be created by hand
in the `CHORD_DATA_DIRECTORY` location.

```bash
docker run -d \
  --mount type=bind,src=/path/to/chord_data,target=/chord/data \
  --mount type=bind,src=/path/to/chord_tmp,target=/chord/tmp \
  --mount type=bind,src=/usr/share/zoneinfo/Etc/UTC,target=/usr/share/zoneinfo/Etc/UTC \
  [container_id]
```


### Important Log Locations

**NGINX:** `/chord/tmp/nginx/*.log`

**uWSGI:** `/chord/tmp/uwsgi/uwsgi.log`

**Non-WSGI Services:** `/chord/tmp/logs/${SERVICE_ARTIFACT}/*`

**PostgreSQL:** `/chord/tmp/postgresql/postgresql-${PG_VERSION}-main.log`
