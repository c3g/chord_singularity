#!/usr/bin/env python3

import time
import subprocess
import sys

from typing import Dict, List

# noinspection PyUnresolvedReferences
from chord_common import get_runtime_config_vars, get_env_str, main

SLEEP_TIME = 0.5
MAX_WAIT_ITERATIONS = 10 / SLEEP_TIME


def job(services: List[Dict], services_config_path: str):
    for s in services:
        if "wsgi" not in s or s["wsgi"]:
            continue

        config_vars = get_runtime_config_vars(s, services_config_path)

        try:
            pid_file = f"{config_vars['SERVICE_TEMP']}/{config_vars['SERVICE_ARTIFACT']}.pid"
            subprocess.run(f"/bin/bash -c 'pkill -9 -F {pid_file}'", shell=True, check=True)

            max_wait = MAX_WAIT_ITERATIONS
            while max_wait > 0:
                if subprocess.run(f"/bin/bash -c 'kill -0 \"$(cat {pid_file})\"'", shell=True,
                                  stderr=subprocess.DEVNULL).returncode == 1:
                    break

                time.sleep(SLEEP_TIME)
                max_wait -= 1

        except subprocess.CalledProcessError:
            print(f"Error stopping service {config_vars['SERVICE_ARTIFACT']}", file=sys.stderr)


if __name__ == "__main__":
    main(job)
