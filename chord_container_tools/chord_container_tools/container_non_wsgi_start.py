#!/usr/bin/env python3

import subprocess
import sys

from .chord_common import (
    ConfigVars,
    Service,
    ServiceList,
    get_service_command_preamble,
    get_runtime_config_vars,
    get_env_str,
    ContainerJob,
)


def run_command(service: Service, config_vars: ConfigVars) -> str:
    return " && ".join((
        *get_service_command_preamble(service, config_vars),
        f"{get_env_str(service, config_vars)} exec nohup {service['service_runnable']} &>"
        f"{config_vars['SERVICE_LOGS']}/{service['type']['artifact']}.log & "
        f"echo $! > {config_vars['SERVICE_TEMP']}/{config_vars['SERVICE_ARTIFACT']}.pid"
    ))


class ContainerNonWSGIStartJob(ContainerJob):
    def job(self, services: ServiceList) -> None:
        for service in filter(lambda s: "wsgi" in s and not s["wsgi"], services):
            config_vars = get_runtime_config_vars(service)

            try:
                subprocess.run(f"/bin/bash -c '{run_command(service, config_vars)}'", shell=True, check=True)
            except subprocess.CalledProcessError:
                print(f"Error starting service {config_vars['SERVICE_ARTIFACT']}", file=sys.stderr)


job = ContainerNonWSGIStartJob()

if __name__ == "__main__":
    job.main()
