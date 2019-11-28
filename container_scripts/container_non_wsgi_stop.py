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
        subprocess.run(f"/bin/bash -c 'pkill -9 -F "
                       f"{config_vars['SERVICE_TEMP']}/{config_vars['SERVICE_ARTIFACT']}.pid'",
                       shell=True, check=True)


if __name__ == "__main__":
    main(job)
