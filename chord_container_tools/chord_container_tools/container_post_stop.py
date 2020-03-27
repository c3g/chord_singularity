#!/usr/bin/env python3

from .chord_common import BasicCommandHookContainerJob


class ContainerPostStopJob(BasicCommandHookContainerJob):
    # Execute post-stop hook commands for any services which have them
    commands_key = "post_stop_commands"


job = ContainerPostStopJob()

if __name__ == "__main__":
    job.main()
