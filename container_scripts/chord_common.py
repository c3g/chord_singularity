import json
import os
import sys

from jsonschema import validate
from typing import Callable, Dict, List


def get_config_vars(s: Dict) -> Dict:
    return {
        "CHORD_ENV": "/chord/tmp/env",  # TODO: Should this be in tmp?

        "SERVICE_SOCKET": f"/chord/tmp/{s['id']}.sock",
        "SERVICE_VENV": f"/chord/services/{s['id']}/env",
        "SERVICE_BASE_URL": f"/api/{s['id']}",

        "SERVICE_DATA": f"/chord/data/{s['id']}",
        "SERVICE_LOGS": f"/chord/tmp/logs/{s['id']}",
        "SERVICE_TEMP": f"/chord/tmp/data/{s['id']}"
    }


def main(job: Callable[[List[Dict]], None]):
    args = sys.argv[1:]

    if len(args) != 1:
        print(f"Usage: {sys.argv[0]} chord_services.json")
        exit(1)

    if os.environ.get("SINGULARITY_CONTAINER", "") == "":
        print(f"Error: {sys.argv[0]} cannot be run outside of a Singularity container.")
        exit(1)

    with open("./chord_services.schema.json") as cf, open(args[0], "r") as sf:
        schema = json.load(cf)
        services = json.load(sf)

        validate(instance=services, schema=schema)

        job(services)
