import json
import random
import os
import subprocess
import sys

from jsonschema import validate
from typing import Callable, Dict, List


SECRET_CHARACTERS = "abcdefghijklmnopqrstuvwxyz0123456789"
SECRET_LENGTH = 64
INSTANCE_CONFIG_PATH = "/chord/tmp/instance_config.json"
RUNTIME_CONFIG_PATH = "/chord/data/.runtime_config.json"  # TODO: How to lock this down? It has sensitive stuff...


def json_load_dict_or_empty(path: str) -> Dict:
    return json.load(open(path, "r")) if os.path.exists(path) else {}


def generate_secret_key() -> str:
    return "".join(random.choice(SECRET_CHARACTERS) for _ in range(SECRET_LENGTH))


def get_config_vars(s: Dict, services_config_path: str) -> Dict:
    config = json_load_dict_or_empty(services_config_path)

    if s["id"] not in config:
        # This should only happen when the image is being built.

        config[s["id"]] = {
            "CHORD_DEBUG": "True",  # TODO: Configure based on production release

            "REDIS_SOCKET": "/chord/tmp/redis.sock",

            "POSTGRES_SOCKET": "/chord/tmp/postgresql/.s.PGSQL.5433",
            "POSTGRES_SOCKET_DIR": "/chord/tmp/postgresql",
            "POSTGRES_PORT": "5433",
            "POSTGRES_DATABASE": f"{s['id']}_db",
            "POSTGRES_USER": f"{s['id']}_acct",

            "SERVICE_ID": s["id"],
            "SERVICE_SOCKET": f"/chord/tmp/{s['id']}.sock",
            "SERVICE_VENV": f"/chord/services/{s['id']}/env",
            "SERVICE_URL_BASE_PATH": f"/api/{s['id']}",

            "SERVICE_DATA": f"/chord/data/{s['id']}",
            "SERVICE_LOGS": f"/chord/tmp/logs/{s['id']}",
            "SERVICE_TEMP": f"/chord/tmp/data/{s['id']}",

            "SERVICE_ENVIRONMENT": f"/chord/data/{s['id']}/.environment",
        }

        json.dump(config, open(services_config_path, "w"))
        subprocess.run(("chmod", "644", services_config_path))  # TODO: How to secure properly?

    return config[s["id"]]


def get_runtime_config_vars(s: Dict, services_config_path: str) -> Dict:
    """Should only be run from inside an instance."""

    instance_config = json_load_dict_or_empty(INSTANCE_CONFIG_PATH)
    services_config = json.load(open(services_config_path, "r"))
    runtime_config = json_load_dict_or_empty(RUNTIME_CONFIG_PATH)

    if s["id"] not in runtime_config:
        # Generate Secrets
        # This should only happen the first time a node is launched.
        runtime_config[s["id"]] = {
            "POSTGRES_PASSWORD": generate_secret_key(),  # Generate a password to be used for the Postgres user
            "SERVICE_SECRET_KEY": generate_secret_key()  # Generate a general-purpose secret key
        }

    json.dump(runtime_config, open(RUNTIME_CONFIG_PATH, "w"))
    subprocess.run(("chmod", "600", RUNTIME_CONFIG_PATH))

    return {**instance_config, **services_config[s["id"]], **runtime_config[s["id"]]}


def format_env_pair(k, v, escaped=False):
    return "{}='{}'".format(k, v.replace("'", r"'\''")) if escaped else f"{k}={v}"


def get_env_str(s, config_vars, escaped=True):
    return (" ".join(format_env_pair(k, v.format(**config_vars), escaped) for k, v in s["python_environment"].items())
            if "python_environment" in s else "")


def main(job: Callable[[List[Dict], str], None]):
    args = sys.argv[1:]

    if len(args) != 2:
        print(f"Usage: {sys.argv[0]} chord_services.json chord_services_config.json")
        exit(1)

    if os.environ.get("SINGULARITY_CONTAINER", "") == "":
        print(f"Error: {sys.argv[0]} cannot be run outside of a Singularity container.")
        exit(1)

    with open("/chord/chord_services.schema.json") as cf, open(args[0], "r") as sf:
        schema = json.load(cf)
        services = json.load(sf)

        validate(instance=services, schema=schema)

        job(services, args[1])
