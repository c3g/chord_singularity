==========
CHORD plan
==========

CHORD Service Registry
----------------------

Type: unregistered

* Implements GA4GH Service Registry Spec

* Loads services from chord-services.json into a SQLite DB

* If chordServiceID not in DB, generate a new GUID for service in this CHORD context, delete ones
  that are no longer present

* Additional metadata:

  * chordServiceID: unique human-readable ID for service (ex. rnaget)
  * chordServiceType: other or data

chord_services.json spec
""""""""""""""""""""""""

.. code-block:: json

   [
       {
           "id": "services",
           "type": "other",
           "repository": "http://...",
           "internal_port": 5001,
           "apt_dependencies": [],
           "python_module": "chord_service_registry",
           "python_callable": "app",
           "python_args": ["TODO"]
       },
       {
           "id": "rnaget",
           "type": "data",
           "repository": "http://",
           "internal_port": 3000,
           "apt_dependencies": [],
           "python_module": "candig_rnaget",
           "python_callable": "app",
           "python_args": ["TODO"]
       }
   ]

ARE WE ALLOWED TO PULL FROM REPOSITORIES OR IS THAT TOO MUCH OF A VULNERABILITY? MAYBE PIP...

TODO: SOME WAY TO SPECIFY INGESTION SCRIPTS... WITH A STANDARDIZED FORMAT

all services must have a requirements.txt, implement /service-info and be able to take --port as an argument

should run everything with uWSGI...

python script needed to parse and run apt, generate nginx conf file for chord proxy, ...

* collect deduplicated apt dependencies and install
* clone each service into /chord/services/
* create virtual environments for each
* generate chord.conf NGINX configuration with all different servers as reverse proxies
* create upstart / systemd service files for each service + reverse proxy
* start all services and then start reverse proxy

How do updates work?
* git pull for each service
* call some regeneration script which does apt dependencies + steps 3-n above

TODO: HOW TO DO SEARCH / SEARCH DISCOVERY???

Search can be done perhaps with existing GA4GH search API
Discovering fields however...
