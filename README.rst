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
------------------------

.. code-block:: json

   [
       {
           "id": "services",
           "type": "other",
           "repository": "http://...",
           "apt_dependencies": [],
           "python_module": "chord_service_registry",
           "python_callable": "app",
           "python_args": ["TODO"]
       },
       {
           "id": "rnaget",
           "type": "data",
           "repository": "http://",
           "apt_dependencies": [],
           "python_module": "candig_rnaget",
           "python_callable": "app",
           "python_args": ["TODO"]
       }
   ]

ARE WE ALLOWED TO PULL FROM REPOSITORIES OR IS THAT TOO MUCH OF A VULNERABILITY? MAYBE PIP...

TODO: SOME WAY TO SPECIFY INGESTION SCRIPTS... WITH A STANDARDIZED FORMAT

All services must have a requirements.txt, implement /service-info and be able to take --port as an argument

How do updates work?

* git pull for each service
* call some regeneration script which does apt dependencies + steps 3-n above

TODO: HOW TO DO SEARCH / SEARCH DISCOVERY???

Search can be done perhaps with existing GA4GH search API
Discovering fields however...
