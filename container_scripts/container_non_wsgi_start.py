#!/usr/bin/env python3

import subprocess
from typing import Dict, List

# noinspection PyUnresolvedReferences
from chord_common import get_runtime_config_vars, get_env_str, main


def job(services: List[Dict], services_config_path: str):
    for s in services:
        if "wsgi" not in s or s["wsgi"]:
            continue

        config_vars = get_runtime_config_vars(s, services_config_path)
        env_str = get_env_str(s, config_vars)

        # TODO: Deduplicate preamble with container_pre_start
        subprocess.run(f"/bin/bash -c 'source {config_vars['SERVICE_VENV']}/bin/activate && "
                       f"source {config_vars['SERVICE_ENVIRONMENT']} && "
                       f"export $(cut -d= -f1 {config_vars['SERVICE_ENVIRONMENT']}) && "  # Export sourced variables
                       f"{env_str} nohup {s['python_runnable']} &> {config_vars['SERVICE_LOGS']}/{s['id']}.log &'",
                       shell=True, check=True)


if __name__ == "__main__":
    main(job)
