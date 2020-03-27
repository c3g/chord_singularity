#!/usr/bin/env python3

from .chord_common import BasicCommandHookContainerJob


class ContainerPostStartJob(BasicCommandHookContainerJob):
    # Execute post-start hook commands for any services which have them
    commands_key = "post_start_commands"


job = ContainerPostStartJob()

if __name__ == "__main__":
    job.main()
