==========
CHORD plan
==========

CHORD Data to Support
---------------------

* Variants

* RNAseq data

* TODO

CHORD Search Description
------------------------

The CHORD search endpoint roughly looks like this:

POST ``/search``
^^^^^^^^^^^^^^^^

Request:

.. code-block:: json

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

``field`` is a dot-notation accessor for the field in question. ``[dataset object]`` means the root dataset object, and
``[array item]`` refers to any item in an array.

``operation`` is one of ``eq, lt, le, gt, ge co``.

``negated`` is a boolean which can negate the operation.

``searchValue`` is the value to be searched.

Response:

.. code-block:: json

   [
     {"id" "dataset_1", "data_type": "some_type"},
     {"id" "dataset_2", "data_type": "some_type"}
   ]

CHORD Service Registry
----------------------

* Implements GA4GH Service Registry Spec

* Loads services from chord-services.json into a SQLite DB

* If chordServiceID not in DB, generate a new GUID for service in this CHORD
  context, delete ones that are no longer present

* Additional metadata:

  * chordServiceID: unique human-readable ID for service (ex. rnaget)
  * chordServiceType: other or data

TODO: SHOULD WE PULL DIRECTLY FROM REPOSITORIES OR IS THAT TOO MUCH OF A VULNERABILITY? MAYBE PIP...

TODO: SOME WAY TO SPECIFY INGESTION SCRIPTS... WITH A STANDARDIZED FORMAT

All services must have a requirements.txt and implement /service-info.

How do updates work?

* ``pip install -U`` for each service
* call some regeneration script which re-checks ``apt`` dependencies + runs steps 3-n above

TODO: HOW TO DO SEARCH / SEARCH DISCOVERY? - Search can be done perhaps with WIP GA4GH search API.

Development
-----------

Setup
^^^^^

To install Singularity, follow the `Singularity installation guide`_.

.. _`Singularity installation guide`: https://sylabs.io/guides/3.3/user-guide/installation.html

To create the virtual environment::

    virtualenv -p python3 ./env
    source env/bin/activate
    pip install -r requirements.txt

NGINX can be set up as a reverse proxy outside of the containers to create a
development CHORD cluster.

Example Dev. NGINX Configuration
""""""""""""""""""""""""""""""""

Configuration for a development CHORD cluster, to use with ``dev_utils.py``::

    server {
        listen 80;

        server_name ~^(\d+)\.chord\.dlougheed\.com$;

        location / {
            proxy_pass http://unix:/tmp/chord/$1/nginx.sock;
        }
    }


This configuration assumes that ``*.chord.dlougheed.com`` (in this example) has
a DNS record set up to point at 127.0.0.1.


Building
^^^^^^^^

To build the image::

    ./dev_utils.py build

You will be asked for your password by Singularity.


Running a Development Cluster
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Assumes ``/tmp/chord`` and ``~/chord_data`` are writable directories.

To run a development cluster with ``n`` nodes, where ``n`` is some positive integer::

    ./dev_utils.py --cluster n start

Other available actions for ``./dev_utils.py`` are ``stop`` and ``restart``.
