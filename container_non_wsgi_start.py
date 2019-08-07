#!/usr/bin/env python3

import subprocess
from typing import Dict, List
from chord_common import get_config_vars, main


def job(services: List[Dict]):
    for s in services:
        if "wsgi" not in s or s["wsgi"]:
            continue

        config_vars = get_config_vars(s)

        env_str = (" ".join(f"{k}={v.format(**config_vars)}" for k, v in s["python_environment"].items())
                   if "python_environment" in s else "")

        subprocess.run(f"/bin/bash -c 'source {config_vars['SERVICE_VENV']}/bin/activate && "
                       f"source {config_vars['CHORD_ENV']} && "
                       f"{env_str} nohup {s['python_runnable']} &> {config_vars['SERVICE_LOGS']}/{s['id']}.log &'",
                       shell=True, check=True)


if __name__ == "__main__":
    main(job)
