==========
CHORD plan
==========

CHORD Service Registry
----------------------

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

TODO: SHOULD WE PULL DIRECTLY FROM REPOSITORIES OR IS THAT TOO MUCH OF A VULNERABILITY? MAYBE PIP...

TODO: SOME WAY TO SPECIFY INGESTION SCRIPTS... WITH A STANDARDIZED FORMAT

All services must have a requirements.txt and implement /service-info.

How do updates work?

* ``pip install -U`` for each service
* call some regeneration script which re-checks ``apt`` dependencies + runs steps 3-n above

TODO: HOW TO DO SEARCH / SEARCH DISCOVERY? - Search can be done perhaps with WIP GA4GH search API.
