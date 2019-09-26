#!/usr/bin/env python3

import subprocess
# noinspection PyUnresolvedReferences
from chord_common import get_config_vars, get_env_str, main


def job(services):
    for s in services:
        config_vars = get_config_vars(s)

        # Create required directories if needed at startup
        subprocess.run(("mkdir", "-p", config_vars["SERVICE_DATA"]), check=True)
        subprocess.run(("mkdir", "-p", config_vars["SERVICE_LOGS"]), check=True)
        subprocess.run(("mkdir", "-p", config_vars["SERVICE_TEMP"]), check=True)

        # Postgres setup
        #  - Create a user with the service ID as the username
        #  - Create a database with cs_{service ID} as the database name
        #  - Only let the owner connect to the database
        # TODO: Create with password, store somewhere secure/locked down
        subprocess.run(("createuser", "-D", "-R", "-S", "-h", config_vars["POSTGRES_SOCKET_DIR"], "-p", "5433",
                        config_vars["POSTGRES_USER"]))
        subprocess.run(("createdb", "-O", config_vars["POSTGRES_USER"], config_vars["POSTGRES_DATABASE"]))
        subprocess.run(("psql", "-U", config_vars["POSTGRES_USER"], "-d", config_vars["POSTGRES_DATABASE"], "-c",
                        f"REVOKE CONNECT ON DATABASE {config_vars['POSTGRES_DATABASE']} FROM PUBLIC;"))

        env_str = get_env_str(s, config_vars)

        pre_start_commands = s.get("pre_start_commands", [])
        for command in pre_start_commands:
            subprocess.run(f"/bin/bash -c 'source {config_vars['SERVICE_VENV']}/bin/activate && "
                           f"source {config_vars['CHORD_ENV']} && "
                           f"{env_str} {command.format(**config_vars)}'", shell=True, check=True)


if __name__ == "__main__":
    main(job)
