#!/usr/bin/env python3

from .chord_common import ServiceList, execute_runtime_commands, ContainerJob


class ContainerPostStartJob(ContainerJob):
    def job(self, services: ServiceList):
        # Execute post-start hook commands for any services which have them
        for s in services:
            execute_runtime_commands(s, s.get("post_start_commands", ()))


job = ContainerPostStartJob()

if __name__ == "__main__":
    job.main()
