#!/usr/bin/env python3

import os
import subprocess
import sys

from typing import Dict, List

from .chord_common import (
    get_service_command_preamble,
    bash_escape_single_quotes,
    get_runtime_config_vars,
    get_env_str,
    format_env_pair,
    main,
)


NEW_DATABASE = os.environ.get("NEW_DATABASE", "False")


def job(services: List[Dict]):
    for s in services:
        config_vars = get_runtime_config_vars(s)

        # Create required directories if needed at startup
        subprocess.run(("mkdir", "-p", config_vars["SERVICE_DATA"]), check=True)
        subprocess.run(("mkdir", "-p", config_vars["SERVICE_LOGS"]), check=True)
        subprocess.run(("mkdir", "-p", config_vars["SERVICE_TEMP"]), check=True)

        # Write environment to the file system
        with open(config_vars["SERVICE_ENVIRONMENT"], "w") as ef:
            for c, v in config_vars.items():
                ef.write(format_env_pair(c, v, escaped=False))
                ef.write("\n")

        subprocess.run(("chmod", "600", config_vars["SERVICE_ENVIRONMENT"]))

        # Postgres setup
        #  - Create a user with the service ID as the username
        #  - Create a database with cs_{service ID} as the database name
        #  - Only let the owner connect to the database
        # TODO: Store password somewhere secure/locked down
        if NEW_DATABASE == "True":
            subprocess.run(("createuser", "-D", "-R", "-S", "-h", config_vars["POSTGRES_SOCKET_DIR"], "-p",
                            config_vars["POSTGRES_PORT"], config_vars["POSTGRES_USER"]))
            subprocess.run(("createdb", "-O", config_vars["POSTGRES_USER"], config_vars["POSTGRES_DATABASE"]))

            subprocess.run(("psql", "-d", config_vars["POSTGRES_DATABASE"], "-c",
                            f"REVOKE CONNECT ON DATABASE {config_vars['POSTGRES_DATABASE']} FROM PUBLIC;"))

            subprocess.run(("psql", "-d", config_vars["POSTGRES_DATABASE"], "-c",
                            f"ALTER USER {config_vars['POSTGRES_USER']} ENCRYPTED PASSWORD "
                            f"'{config_vars['POSTGRES_PASSWORD']}'"))

        for command in s.get("pre_start_commands", ()):
            commands = (*get_service_command_preamble(s, config_vars),
                        f"{get_env_str(s, config_vars)} {bash_escape_single_quotes(command.format(**config_vars))}")

            full_command = f"/bin/bash -c '{' && '.join(commands)}'"

            try:
                subprocess.run(full_command, shell=True, check=True)
            except subprocess.CalledProcessError as e:
                print(e, file=sys.stderr)


def entry():
    main(job)


if __name__ == "__main__":
    entry()
