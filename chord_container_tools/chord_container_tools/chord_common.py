import json
import random
import os
import subprocess
import sys
import uuid

from abc import ABC, abstractmethod
from jsonschema import validate
from typing import Dict, List, Iterable, Tuple


__all__ = [
    "TYPE_PYTHON",
    "TYPE_JAVASCRIPT",

    "CHORD_SERVICES_SCHEMA_PATH",

    "SECRET_CHARACTERS",
    "SECRET_LENGTH",
    "AUTH_CONFIG_PATH",
    "INSTANCE_CONFIG_PATH",
    "RUNTIME_CONFIG_PATH",
    "CHORD_ENVIRONMENT_PATH",

    "ConfigVars",
    "Service",
    "ServiceList",

    "json_load_dict_or_empty",
    "load_services",
    "generate_secret_key",
    "get_config_vars",
    "get_runtime_common_chord_environment",
    "get_runtime_config_vars",
    "get_service_command_preamble",
    "execute_runtime_command",
    "execute_runtime_commands",
    "bash_escape_single_quotes",
    "format_env_pair",
    "get_env_str",
    "write_environment_dict_to_path",

    "ContainerJob",
]


TYPE_PYTHON = "python"
TYPE_JAVASCRIPT = "javascript"

CHORD_SERVICES_PATH = "/chord/chord_services.json"
CHORD_SERVICES_SCHEMA_PATH = "/chord/chord_services.schema.json"
CHORD_SERVICES_CONFIG_PATH = "/chord/chord_services_config.json"

SECRET_CHARACTERS = "abcdefghijklmnopqrstuvwxyz0123456789"
SECRET_LENGTH = 64
AUTH_CONFIG_PATH = "/chord/data/.auth_config.json"  # TODO: How to lock this down? It has sensitive stuff...
INSTANCE_CONFIG_PATH = "/chord/data/.instance_config.json"  # TODO: Rename
RUNTIME_CONFIG_PATH = "/chord/data/.runtime_config.json"  # TODO: How to lock this down? It has sensitive stuff...
CHORD_ENVIRONMENT_PATH = "/chord/data/.environment"


ConfigVars = Dict[str, str]
Service = Dict
ServiceList = List[Service]


def json_load_dict_or_empty(path: str) -> Dict:
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}


def json_save(obj, path: str):
    with open(path, "w") as f:
        json.dump(obj, f)


def load_services() -> ServiceList:
    with open(CHORD_SERVICES_PATH, "r") as f:
        return [s for s in json.load(f) if not s.get("disabled", False)]


def generate_secret_key() -> str:
    return "".join(random.choice(SECRET_CHARACTERS) for _ in range(SECRET_LENGTH))


def get_config_vars(s: Dict) -> ConfigVars:
    config = json_load_dict_or_empty(CHORD_SERVICES_CONFIG_PATH)

    s_artifact = s["type"]["artifact"]

    if s_artifact not in config:
        # This should only happen when the image is being built.

        config[s_artifact] = {
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

        json_save(config, CHORD_SERVICES_CONFIG_PATH)
        subprocess.run(("chmod", "644", CHORD_SERVICES_CONFIG_PATH))  # TODO: How to secure properly?

    return config[s_artifact]


def get_runtime_common_chord_environment() -> ConfigVars:
    """Should only be run from inside an instance."""
    auth_config = json_load_dict_or_empty(AUTH_CONFIG_PATH)
    return {
        "OIDC_DISCOVERY_URI": auth_config["OIDC_DISCOVERY_URI"],
        **json_load_dict_or_empty(INSTANCE_CONFIG_PATH)
    }


def get_runtime_config_vars(s: Service) -> ConfigVars:
    """Should only be run from inside an instance."""

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

    json_save(runtime_config, RUNTIME_CONFIG_PATH)
    subprocess.run(("chmod", "600", RUNTIME_CONFIG_PATH))

    return {
        **get_runtime_common_chord_environment(),
        **json_load_dict_or_empty(CHORD_SERVICES_CONFIG_PATH)[s_artifact],
        **runtime_config[s_artifact]
    }


def get_service_command_preamble(service: Service, config_vars: ConfigVars) -> Iterable[str]:
    if service["type"]["language"] == TYPE_PYTHON:
        yield f"source {config_vars['SERVICE_VENV']}/bin/activate"

    yield f"source {config_vars['SERVICE_ENVIRONMENT']}"
    yield f"export $(cut -d= -f1 {config_vars['SERVICE_ENVIRONMENT']})"


def execute_runtime_command(s: Service, command: str):
    config_vars = get_runtime_config_vars(s)

    commands = (*get_service_command_preamble(s, config_vars),
                f"{get_env_str(s, config_vars)} {bash_escape_single_quotes(command.format(**config_vars))}")

    full_command = f"/bin/bash -c '{' && '.join(commands)}'"

    try:
        subprocess.run(full_command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(e, file=sys.stderr)


def execute_runtime_commands(s: Service, commands: Tuple[str]):
    for command in commands:
        execute_runtime_command(s, command)


def bash_escape_single_quotes(v):
    return v.replace("'", r"'\''")


def format_env_pair(k: str, v: str, escaped=False):
    return "{}='{}'".format(k, bash_escape_single_quotes(v)) if escaped else f"{k}={v}"


def get_env_str(s: Service, config_vars: ConfigVars, escaped=True):
    return (" ".join(format_env_pair(k, v.format(**config_vars), escaped) for k, v in s["run_environment"].items())
            if "run_environment" in s else "")


def write_environment_dict_to_path(env: Dict[str, str], path: str, export: bool = False):
    with open(path, "w") as ef:
        for c, v in env.items():
            if export:
                ef.write("export ")
            ef.write(format_env_pair(c, v, escaped=False))
            ef.write("\n")


class ContainerJob(ABC):
    def __init__(self, build=False):
        self.build = build

    def main(self):
        if len(sys.argv) != 1:
            print(f"Usage: {sys.argv[0]}")
            exit(1)

        singularity_env = "SINGULARITY_ENVIRONMENT" if self.build else "SINGULARITY_CONTAINER"

        if os.environ.get(singularity_env, "") == "" and os.environ.get("CHORD_DOCKER_BUILD", "") == "":
            print(f"Error: {sys.argv[0]} cannot be run outside of a Singularity or Docker container.")
            exit(1)

        with open(CHORD_SERVICES_SCHEMA_PATH) as cf:
            schema = json.load(cf)
            services = load_services()

            validate(instance=services, schema=schema)

            self.job(services)

    @abstractmethod
    def job(self, services: ServiceList):
        pass
