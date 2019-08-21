#!/usr/bin/env python3

import argparse
import os
import subprocess


def action_start(args):
    for i in range(1, args.cluster_size + 1):
        print(f"[CHORD DEV UTILS] Starting instance {i}...")

        subprocess.run(["mkdir", "-p", f"/tmp/chord/{i}"])

        with open(f"/tmp/chord/{i}/env", "w") as f:
            f.write(f"export CHORD_URL=http://{i}.chord.dlougheed.com/\n")
            f.write("export CHORD_REGISTRY_URL=http://1.chord.dlougheed.com/\n")

        user_dir = os.path.expanduser("~")
        subprocess.run(["mkdir", "-p", os.path.join(user_dir, f"chord_data/{i}")])
        subprocess.run(["singularity", "instance", "start",
                        "--bind", f"/tmp/chord/{i}:/chord/tmp",
                        "--bind", os.path.join(user_dir, f"chord_data/{i}") + ":/chord/data",
                        "chord.sif", f"chord{i}"])


def action_stop(args):
    for i in range(1, args.cluster_size + 1):
        print(f"[CHORD DEV UTILS] Stopping instance {i}...")
        subprocess.run(["singularity", "instance", "stop", f"chord{i}"])


def main():
    parser = argparse.ArgumentParser(description="Helpers for CHORD server development.")
    parser.add_argument("--cluster-size", dest="cluster_size", type=int, default=1)
    parser.add_argument("action", metavar="action", type=str, choices=["build", "start", "stop", "restart"],
                        help="build|start|stop|restart")
    args = parser.parse_args()

    if args.action == "build":
        subprocess.run(["sudo", "singularity", "build", "chord.sif", "chord.def"])

    elif args.action == "start":
        action_start(args)

    elif args.action == "stop":
        action_stop(args)

    elif args.action == "restart":
        action_stop(args)
        action_start(args)


if __name__ == "__main__":
    main()
