#!/usr/bin/env python3

import subprocess
# noinspection PyUnresolvedReferences
from chord_common import get_config_vars, get_env_str, main


def job(services):
    for s in services:
        subprocess.run(["mkdir", "-p", f"/chord/data/{s['id']}"], check=True)
        subprocess.run(["mkdir", "-p", f"/chord/tmp/logs/{s['id']}"], check=True)
        subprocess.run(["mkdir", "-p", f"/chord/tmp/data/{s['id']}"], check=True)

        config_vars = get_config_vars(s)
        env_str = get_env_str(s, config_vars)

        pre_start_commands = s.get("pre_start_commands", [])
        for command in pre_start_commands:
            subprocess.run(f"/bin/bash -c 'source {config_vars['SERVICE_VENV']}/bin/activate && "
                           f"source {config_vars['CHORD_ENV']} && "
                           f"{env_str} {command.format(**config_vars)}'", shell=True, check=True)


if __name__ == "__main__":
    main(job)
