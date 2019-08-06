==========
CHORD plan
==========

CHORD Data to Support
---------------------

* Variants

* RNAseq data

* TODO

CHORD Service Registry
----------------------

* Implements GA4GH Service Registry Spec

* Loads services from chord-services.json into a SQLite DB

* If chordServiceID not in DB, generate a new GUID for service in this CHORD context, delete ones
  that are no longer present

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

Example Dev. NGINX Configuration
--------------------------------

Configuration for a development CHORD cluster, to use with ``dev_utils.py``::

    server {
        listen 80;

        server_name ~^(\d+)\.chord\.dlougheed\.com$;

        location / {
            proxy_pass http://unix:/tmp/chord/$1/nginx.sock;
        }
    }
