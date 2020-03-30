#!/usr/bin/env python3

from .chord_common import ServiceList, execute_runtime_command, ContainerJob


class ContainerNonWSGIStartJob(ContainerJob):
    def job(self, services: ServiceList) -> None:
        for service in filter(lambda s: not s.get("wsgi", True), services):
            execute_runtime_command(service, (
                f"exec nohup {service['service_runnable']} &> {{SERVICE_LOGS}}/{{SERVICE_ARTIFACT}}.log & "
                f"echo $! > {{SERVICE_TEMP}}/{{SERVICE_ARTIFACT}}.pid"
            ))


job = ContainerNonWSGIStartJob()

if __name__ == "__main__":
    job.main()
