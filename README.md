# CHORD Singularity

![Build Status](https://travis-ci.org/c3g/chord_singularity.svg?branch=master)

What's included in a CHORD Singularity container?

  * NodeJS 12
  * Python 3.7
  * Java 11
  * A Redis instance running at `/chord/tmp/redis.sock`
  * A PostgreSQL 11 instance running at `/chord/tmp/postgresql/.s.PGSQL.5433`, with a username stored in the
    environment variable `POSTGRES_USER` and a service-specific database stored in the environment variable
    `POSTGRES_DATABASE`
  * `zlib1g-dev`, `libbz2-dev`, and `liblzma-dev`
  * `htslib`

**Note:** Google DNS servers are used to resolve OIDC IdP domain names.


## Development

### Setup

To install Singularity, follow the
[Singularity installation guide](https://sylabs.io/guides/3.4/user-guide/installation.html).

To create the virtual environment:

```bash
virtualenv -p python3 ./env
source env/bin/activate
pip install -r requirements.txt
```

NGINX can be set up as a reverse proxy outside of the containers to create a
development CHORD cluster.

#### Example Dev. NGINX Configuration

Configuration for a development CHORD cluster, to use with `dev_utils.py`:

```nginx
server {
    listen 80;

    server_name ~^(\d+)\.chord\.dlougheed\.com$;

    location / {
        # Tweak these as needed for the security concerns of the instance.
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' '*' always;
        add_header 'Access-Control-Allow-Headers' '*' always;

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


### Needed files in the CHORD `data` folder

**These files are automatically created by the `dev_utils.py` script, but
should be set up in another way for production deployment.**

Values for `.auth_config.json` are read from the
[`instance_auth.json`](instance_auth.json) file at instance start time when
using `dev_utils.py`.

  * `.instance_config.json`, containing the following key-value pairs:
    * `CHORD_HOST` - The domain name of the host (no http://, no trailing slash)
    * `CHORD_URL` - The URL of the node (for federation), with trailing slash
    * `CHORD_REGISTRY_URL` - The URL of the registry node (for federation), with trailing slash
  * `.auth_config.json`:
    * `OIDC_DISCOVERY_URI`: The discovery URI (typically
      `.../.well_known/openid-configuration`) for the OIDC IdP
    * `CLIENT_ID`: The client ID for the node in the OIDC IdP
    * `CLIENT_SECRET`: The client secret for the node in the OIDC IdP
    * `OWNER_SUB`: The subject ID (from the OIDC IdP) of the node's owner


### Building

**Building only works on Linux-based operating systems.**

To build the image:

```bash
./dev_utils.py build
```

You will be asked for your password by Singularity.


### Running a Development Cluster

Assumes `/tmp/chord` and `~/chord_data` are writable directories.

**Note:** CHORD temporary and data directories can be specified by editing `dev_utils.py` (not recommended) or setting
`CHORD_DATA_DIRECTORY` and `CHORD_TEMP_DIRECTORY` when running `dev_utils.py`.

To run a development cluster with `n` nodes, where `n` is some positive integer:

```bash
./dev_utils.py --cluster n start
```

Other available actions for `./dev_utils.py` are `stop` and `restart`.
