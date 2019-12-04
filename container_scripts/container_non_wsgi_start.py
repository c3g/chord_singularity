#!/usr/bin/env python3

import subprocess
import sys

from typing import Dict, List

# noinspection PyUnresolvedReferences
from chord_common import (
    get_service_command_preamble,
    get_runtime_config_vars,
    get_env_str,
    main,

    TYPE_PYTHON,
    TYPE_JAVASCRIPT,
)


def run_command(service, config_vars):
    return " && ".join((
        *get_service_command_preamble(service, config_vars),
        f"{get_env_str(service, config_vars)} exec nohup {service['service_runnable']} &>"
        f"{config_vars['SERVICE_LOGS']}/{service['type']['artifact']}.log & "
        f"echo $! > {config_vars['SERVICE_TEMP']}/{config_vars['SERVICE_ARTIFACT']}.pid"
    ))


def job(services: List[Dict], services_config_path: str):
    for s in services:
        if "wsgi" not in s or s["wsgi"]:
            continue

        config_vars = get_runtime_config_vars(s, services_config_path)

        try:
            subprocess.run(f"/bin/bash -c '{run_command(s, config_vars)}'", shell=True, check=True)
        except subprocess.CalledProcessError:
            print(f"Error starting service {config_vars['SERVICE_ARTIFACT']}", file=sys.stderr)


if __name__ == "__main__":
    main(job)
