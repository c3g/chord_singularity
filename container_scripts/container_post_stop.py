#!/usr/bin/env python3

import subprocess
import sys

from typing import Dict, List

# noinspection PyUnresolvedReferences
from chord_common import get_runtime_config_vars, get_env_str


def job(services: List[Dict], services_config_path: str):
    for s in services:
        config_vars = get_runtime_config_vars(s, services_config_path)
        env_str = get_env_str(s, config_vars)

        stop_commands = s.get("post_stop_commands", ())
        for command in stop_commands:
            full_command = (  # TODO: Deduplicate preamble with container_non_wsgi_start
                f"/bin/bash -c 'source {config_vars['SERVICE_VENV']}/bin/activate && "
                f"source {config_vars['SERVICE_ENVIRONMENT']} && "
                f"export $(cut -d= -f1 {config_vars['SERVICE_ENVIRONMENT']}) && "  # Export sourced variables
                f"{env_str} {command.format(**config_vars)}'"
            )

            try:
                subprocess.run(full_command, shell=True, check=True)
            except subprocess.CalledProcessError:
                print(f"Error running command: \n\t{full_command}", file=sys.stderr)
