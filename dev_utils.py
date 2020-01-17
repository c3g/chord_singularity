#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys


USER_DIR = os.path.expanduser("~")
CHORD_DATA_DIRECTORY = os.environ.get("CHORD_DATA_DIRECTORY", os.path.join(USER_DIR, "chord_data"))
CHORD_TEMP_DIRECTORY = os.environ.get("CHORD_TEMP_DIRECTORY", "/tmp/chord")

CHORD_AUTH_CONFIG_FILE = ".auth_config.json"
CHORD_INSTANCE_CONFIG_FILE = ".instance_config.json"

with open("instance_auth.json", "r") as f:
    instance_auth = json.load(f)


def get_instance_name(i: int):
    return f"chord{i}"


def get_instance_host(i: int):
    return f"{i}.chord.dlougheed.com"


def action_start(args):
    for i in range(1, args.cluster_size + 1):
        instance_host = get_instance_host(i)
        if instance_host not in instance_auth:
            print(f"[CHORD DEV UTILS] Cannot find auth configuration for instance {instance_host}", file=sys.stderr)
            exit(1)

    for i in range(1, args.cluster_size + 1):
        print(f"[CHORD DEV UTILS] Starting instance {i}...")

        instance_data = os.path.join(CHORD_DATA_DIRECTORY, str(i))
        instance_temp = os.path.join(CHORD_TEMP_DIRECTORY, str(i))

        subprocess.run(("mkdir", "-p", instance_data, instance_temp))

        instance_host = get_instance_host(i)

        with open(os.path.join(instance_data, CHORD_INSTANCE_CONFIG_FILE), "w") as fc:
            # TODO: Environment: CHORD_DEBUG, CHORD_PERMISSIONS
            json.dump({
                "CHORD_DEBUG": True,  # Whether the container is started in DEBUG mode
                "CHORD_PERMISSIONS": False,  # Whether the container uses the default permissions system

                "CHORD_HOST": instance_host,
                "CHORD_URL": f"http://{instance_host}/",  # Trailing slash important here
                "CHORD_REGISTRY_URL": "http://1.chord.dlougheed.com/",  # ... and here
            }, fc)

        with open(os.path.join(instance_data, CHORD_AUTH_CONFIG_FILE), "w") as fa:
            json.dump(instance_auth[instance_host], fa)

        subprocess.run(("singularity", "instance", "start",
                        "--bind", f"{instance_temp}:/chord/tmp",
                        "--bind", f"{instance_data}:/chord/data",
                        "--bind", "/usr/share/zoneinfo/Etc/UTC:/usr/share/zoneinfo/Etc/UTC",
                        "chord.sif", get_instance_name(i)))


def action_stop(args):
    for i in range(1, args.cluster_size + 1):
        print(f"[CHORD DEV UTILS] Stopping instance {i}...")
        subprocess.run(("singularity", "exec", f"instance://{get_instance_name(i)}",
                        "bash", "/chord/container_scripts/stop_script.bash"))
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
