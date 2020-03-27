#!/usr/bin/env python3

import time
import subprocess
import sys

from .chord_common import ServiceList, get_runtime_config_vars, ContainerJob

SLEEP_TIME = 0.5  # seconds
MAX_WAIT_TIME = 10  # seconds


class ContainerNonWSGIStopJob(ContainerJob):
    def job(self, services: ServiceList) -> None:
        """
        Stops all non-WSGI services (i.e. services which run their own HTTP server), killing them if needed.
        :param services: List of all services to first filter to only non-WSGI services and then to kill
        """

        for service in filter(lambda s: "wsgi" in s and not s["wsgi"], services):
            config_vars = get_runtime_config_vars(service)

            try:
                # Send a kill signal to the service via pkill and the service's process ID
                pid_file = f"{config_vars['SERVICE_TEMP']}/{config_vars['SERVICE_ARTIFACT']}.pid"
                subprocess.run(f"/bin/bash -c 'pkill -9 -F {pid_file}'", shell=True, check=True)

                wait_iterations = MAX_WAIT_TIME / SLEEP_TIME
                while wait_iterations > 0:
                    if subprocess.run(f"/bin/bash -c 'kill -0 \"$(cat {pid_file})\"'", shell=True,
                                      stderr=subprocess.DEVNULL).returncode == 1:
                        # The process has been killed already, so kill -0 returns 1 -- i.e. we're done
                        break

                    # The kill -0 command exited with status 0, meaning it's currently being attempted - try to wait
                    # until kill has occurred by sleeping and checking the process status again
                    time.sleep(SLEEP_TIME)
                    wait_iterations -= 1

            except subprocess.CalledProcessError:
                print(f"Error stopping service {config_vars['SERVICE_ARTIFACT']}", file=sys.stderr)


job = ContainerNonWSGIStopJob()

if __name__ == "__main__":
    job.main()
