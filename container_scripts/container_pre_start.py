#!/usr/bin/env python3

import subprocess
# noinspection PyUnresolvedReferences
from chord_common import main


def job(services):
    for s in services:
        subprocess.run(["mkdir", "-p", f"/chord/data/{s['id']}"], check=True)
        subprocess.run(["mkdir", "-p", f"/chord/tmp/logs/{s['id']}"], check=True)
        subprocess.run(["mkdir", "-p", f"/chord/tmp/data/{s['id']}"], check=True)


if __name__ == "__main__":
    main(job)
