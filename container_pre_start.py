#!/usr/bin/env python3

import json
import os
import subprocess
import sys

from jsonschema import validate


def main():
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

        for s in services:
            subprocess.run(["mkdir", f"/chord/data/{s['id']}"], check=True)
            subprocess.run(["mkdir", f"/chord/tmp/logs/{s['id']}"], check=True)
            subprocess.run(["mkdir", f"/chord/tmp/data/{s['id']}"], check=True)


if __name__ == "__main__":
    main()
