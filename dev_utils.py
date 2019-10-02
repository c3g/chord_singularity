#!/usr/bin/env python3

import argparse
import os
import subprocess


USER_DIR = os.path.expanduser("~")
CHORD_DATA_DIRECTORY = os.path.join(USER_DIR, "chord_data")
CHORD_TEMP_DIRECTORY = "/tmp/chord"


def get_instance_name(i: int):
    return f"chord{i}"


def action_start(args):
    for i in range(1, args.cluster_size + 1):
        print(f"[CHORD DEV UTILS] Starting instance {i}...")

        instance_data = os.path.join(CHORD_DATA_DIRECTORY, str(i))
        instance_temp = os.path.join(CHORD_TEMP_DIRECTORY, str(i))

        subprocess.run(("mkdir", "-p",  instance_temp))

        with open(os.path.join(instance_temp, "env"), "w") as f:
            f.write(f"export CHORD_URL=http://{i}.chord.dlougheed.com/\n")  # TODO: Should this be a common var?
            f.write("export CHORD_REGISTRY_URL=http://1.chord.dlougheed.com/\n")  # TODO: Above

        subprocess.run(("mkdir", "-p", instance_data))
        subprocess.run(("singularity", "instance", "start",
                        "--bind", f"{instance_temp}:/chord/tmp",
                        "--bind", f"{instance_data}:/chord/data",
                        "chord.sif", get_instance_name(i)))


def action_stop(args):
    for i in range(1, args.cluster_size + 1):
        print(f"[CHORD DEV UTILS] Stopping instance {i}...")
        subprocess.run(("singularity", "instance", "stop", get_instance_name(i)))


def action_shell(args):
    subprocess.run(("singularity", "shell", f"instance://{get_instance_name(args.node)}"))


def main():
    parser = argparse.ArgumentParser(description="Helpers for CHORD server development.")
    parser.add_argument("--cluster-size", dest="cluster_size", type=int, default=1)
    parser.add_argument("--node", dest="node", type=int, help="[node index]", default=1)
    parser.add_argument("action", metavar="action", type=str, choices=("build", "start", "stop", "restart", "shell"),
                        help="build|start|stop|restart|shell")

    args = parser.parse_args()

    if args.action == "build":
        subprocess.run(("sudo", "singularity", "build", "chord.sif", "chord.def"))

    elif args.action == "start":
        action_start(args)

    elif args.action == "stop":
        action_stop(args)

    elif args.action == "restart":
        action_stop(args)
        action_start(args)

    elif args.action == "shell":
        action_shell(args)


if __name__ == "__main__":
    main()
