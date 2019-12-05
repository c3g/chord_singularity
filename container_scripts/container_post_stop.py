#!/usr/bin/env python3

import subprocess
import sys

from typing import Dict, List

# noinspection PyUnresolvedReferences
from chord_common import (
    get_service_command_preamble,
    bash_escape_single_quotes,
    get_runtime_config_vars,
    get_env_str,
    main,
)


def job(services: List[Dict], services_config_path: str):
    for s in services:
        config_vars = get_runtime_config_vars(s, services_config_path)

        for command in s.get("post_stop_commands", ()):
            commands = (*get_service_command_preamble(s, config_vars),
                        f"{get_env_str(s, config_vars)} {bash_escape_single_quotes(command.format(**config_vars))}")

            full_command = f"/bin/bash -c '{' && '.join(commands)}'"

            try:
                subprocess.run(full_command, shell=True, check=True)
            except subprocess.CalledProcessError as e:
                print(e, file=sys.stderr)


if __name__ == "__main__":
    main(job)
