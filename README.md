# CHORD Singularity

![Build Status](https://travis-ci.org/c3g/chord_singularity.svg?branch=master)

What's included in a CHORD Singularity container?

  * NodeJS 10
  * Python 3.7
  * Java 11
  * A Redis instance running at `/chord/tmp/redis.sock`
  * A PostgreSQL 11 instance running at `/chord/tmp/postgresql/.s.PGSQL.5433`, with a username stored in the
    environment variable `POSTGRES_USER` and a service-specific database stored in the environment variable
    `POSTGRES_DATABASE`
  * `zlib1g-dev`, `libbz2-dev`, and `liblzma-dev`
  * `htslib`


## CHORD Data to Support

  * Variants
  * RNAseq data
  * TODO


## CHORD Search Description

The CHORD search endpoint roughly looks like this:

### POST `/search`

Request:

```json
{
 "dataTypeID": "some_type",
 "conditions": [
   {
     "field": "[dataset object].some_object.some_property",
     "operation": "eq",
     "negated": false,
     "searchValue": "some_value"
   }
 ]
}
```

`field` is a dot-notation accessor for the field in question. `[dataset object]` means the root dataset object, and
`[array item]` refers to any item in an array.

`operation` is one of `eq, lt, le, gt, ge co`.

`negated` is a boolean which can negate the operation.

`searchValue` is the value to be searched.

Response:

```json
[
 {"id": "dataset_1", "data_type": "some_type"},
 {"id": "dataset_2", "data_type": "some_type"}
]
```


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
        proxy_pass http://unix:/tmp/chord/$1/nginx.sock;
    }
}
```

This configuration assumes that `*.chord.dlougheed.com` (in this example) has
a DNS record set up to point at 127.0.0.1.


### Building

To build the image:

```bash
./dev_utils.py build
```

You will be asked for your password by Singularity.


### Running a Development Cluster

Assumes `/tmp/chord` and `~/chord_data` are writable directories.

To run a development cluster with `n` nodes, where `n` is some positive integer:

```bash
./dev_utils.py --cluster n start
```

Other available actions for `./dev_utils.py` are `stop` and `restart`.
