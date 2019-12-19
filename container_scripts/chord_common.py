import json
import random
import os
import subprocess
import sys
import uuid

from jsonschema import validate
from typing import Callable, Dict, List, Tuple


TYPE_PYTHON = "python"
TYPE_JAVASCRIPT = "javascript"


SECRET_CHARACTERS = "abcdefghijklmnopqrstuvwxyz0123456789"
SECRET_LENGTH = 64
INSTANCE_CONFIG_PATH = "/chord/data/.instance_config.json"
RUNTIME_CONFIG_PATH = "/chord/data/.runtime_config.json"  # TODO: How to lock this down? It has sensitive stuff...


def json_load_dict_or_empty(path: str) -> Dict:
    return json.load(open(path, "r")) if os.path.exists(path) else {}


def generate_secret_key() -> str:
    return "".join(random.choice(SECRET_CHARACTERS) for _ in range(SECRET_LENGTH))


def get_config_vars(s: Dict, services_config_path: str) -> Dict:
    config = json_load_dict_or_empty(services_config_path)

    s_artifact = s["type"]["artifact"]

    if s_artifact not in config:
        # This should only happen when the image is being built.

        config[s_artifact] = {
            "CHORD_DEBUG": "True",  # TODO: Configure based on production release

            "REDIS_SOCKET": "/chord/tmp/redis.sock",

            "POSTGRES_SOCKET": "/chord/tmp/postgresql/.s.PGSQL.5432",
            "POSTGRES_SOCKET_DIR": "/chord/tmp/postgresql",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DATABASE": f"{s_artifact}_db",
            "POSTGRES_USER": f"{s_artifact}_acct",

            "SERVICE_ARTIFACT": s_artifact,
            "SERVICE_SOCKET": f"/chord/tmp/{s_artifact}.sock",
            "SERVICE_VENV": f"/chord/services/{s_artifact}/env",
            "SERVICE_URL_BASE_PATH": f"/api/{s_artifact}",

            "SERVICE_DATA": f"/chord/data/{s_artifact}",
            "SERVICE_LOGS": f"/chord/tmp/logs/{s_artifact}",
            "SERVICE_TEMP": f"/chord/tmp/data/{s_artifact}",

            "SERVICE_ENVIRONMENT": f"/chord/data/{s_artifact}/.environment",
        }

        with open(services_config_path, "w") as scf:
            json.dump(config, scf)

        subprocess.run(("chmod", "644", services_config_path))  # TODO: How to secure properly?

    return config[s_artifact]


def get_runtime_config_vars(s: Dict, services_config_path: str) -> Dict:
    """Should only be run from inside an instance."""

    instance_config = json_load_dict_or_empty(INSTANCE_CONFIG_PATH)
    services_config = json.load(open(services_config_path, "r"))
    runtime_config = json_load_dict_or_empty(RUNTIME_CONFIG_PATH)

    s_artifact = s["type"]["artifact"]

    if s_artifact not in runtime_config:
        # Generate Secrets
        # This should only happen the first time a node is launched.
        runtime_config[s_artifact] = {
            "POSTGRES_PASSWORD": generate_secret_key(),  # Generate a password to be used for the Postgres user
            "SERVICE_SECRET_KEY": generate_secret_key(),  # Generate a general-purpose secret key
            "SERVICE_ID": str(uuid.uuid4())  # Generate a unique UUID for the service
        }

    with open(RUNTIME_CONFIG_PATH, "w") as rcf:
        json.dump(runtime_config, rcf)

    subprocess.run(("chmod", "600", RUNTIME_CONFIG_PATH))

    return {**instance_config, **services_config[s_artifact], **runtime_config[s_artifact]}


def get_service_command_preamble(service: Dict, config_vars: Dict) -> Tuple[str, ...]:
    preamble = (
        f"source {config_vars['SERVICE_ENVIRONMENT']}",
        f"export $(cut -d= -f1 {config_vars['SERVICE_ENVIRONMENT']})",
    )

    if service["type"]["language"] == TYPE_PYTHON:
        preamble = (f"source {config_vars['SERVICE_VENV']}/bin/activate",) + preamble

    return preamble


def bash_escape_single_quotes(v):
    return v.replace("'", r"'\''")


def format_env_pair(k, v, escaped=False):
    return "{}='{}'".format(k, bash_escape_single_quotes(v)) if escaped else f"{k}={v}"


def get_env_str(s, config_vars, escaped=True):
    return (" ".join(format_env_pair(k, v.format(**config_vars), escaped) for k, v in s["run_environment"].items())
            if "run_environment" in s else "")


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
