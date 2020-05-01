#!/usr/bin/env python3

import os
import subprocess

from .chord_common import (
    CHORD_ENVIRONMENT_PATH,
    ConfigVars,
    ServiceList,
    get_runtime_common_chord_environment,
    execute_runtime_commands,
    get_runtime_config_vars,
    write_environment_dict_to_path,
    ContainerJob,
)


NEW_DATABASE = os.environ.get("NEW_DATABASE", "False") == "True"


def create_service_directories_if_needed(config_vars: ConfigVars) -> None:
    subprocess.run(("mkdir", "-p", config_vars["SERVICE_DATA"]), check=True)
    subprocess.run(("mkdir", "-p", config_vars["SERVICE_LOGS"]), check=True)
    subprocess.run(("mkdir", "-p", config_vars["SERVICE_TEMP"]), check=True)


def configure_postgres_if_needed(config_vars: ConfigVars) -> None:
    # Set up Postgres for the service
    # TODO: Store password somewhere secure/locked down

    if not NEW_DATABASE:
        # Not configuring Postgres for the first time
        return

    # Create a service user
    subprocess.run(("createuser", "-D", "-R", "-S", "-h", config_vars["POSTGRES_SOCKET_DIR"], "-p",
                    config_vars["POSTGRES_PORT"], config_vars["POSTGRES_USER"]))

    # Create a service database owned by the service user
    subprocess.run(("createdb", "-O", config_vars["POSTGRES_USER"], config_vars["POSTGRES_DATABASE"]))

    # Prevent other users from connecting to the database
    subprocess.run(("psql", "-d", config_vars["POSTGRES_DATABASE"], "-c",
                    f"REVOKE CONNECT ON DATABASE {config_vars['POSTGRES_DATABASE']} FROM PUBLIC;"))

    # Set the generated password for the service user
    subprocess.run(("psql", "-d", config_vars["POSTGRES_DATABASE"], "-c",
                    f"ALTER USER {config_vars['POSTGRES_USER']} ENCRYPTED PASSWORD "
                    f"'{config_vars['POSTGRES_PASSWORD']}'"))


class ContainerPreStartJob(ContainerJob):
    def job(self, services: ServiceList) -> None:
        """
        Runs a series of pre-service-start actions, for each service, including:
         - Writing common environment variables to a common environment file
         - Creating service directories for data, logs, and temporary files
         - Writing service-specific environment variables to a service environment file
        :param services: List of services from chord_services.json
        """

        # Write common environment variables to a file for later sourcing
        write_environment_dict_to_path(get_runtime_common_chord_environment(), CHORD_ENVIRONMENT_PATH, export=True)

        for s in services:
            config_vars = get_runtime_config_vars(s)

            # Create required directories if needed at startup
            create_service_directories_if_needed(config_vars)

            # Write service-specific environment variables to the file system and lock down its permissions
            write_environment_dict_to_path(config_vars, config_vars["SERVICE_ENVIRONMENT"])
            subprocess.run(("chmod", "600", config_vars["SERVICE_ENVIRONMENT"]))

            # Set up the service's Postgres database if not already set up
            configure_postgres_if_needed(config_vars)

            # Run any chord_services.json specified pre-start commands that may exist
            execute_runtime_commands(s, s.get("pre_start_commands", ()))


job = ContainerPreStartJob()

if __name__ == "__main__":
    job.main()
