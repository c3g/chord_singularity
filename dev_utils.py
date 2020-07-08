#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys

from pathlib import Path


USER_DIR = os.path.expanduser("~")
CHORD_DATA_DIRECTORY = os.environ.get("CHORD_DATA_DIRECTORY", os.path.join(USER_DIR, "chord_data"))
CHORD_TEMP_DIRECTORY = os.environ.get("CHORD_TEMP_DIRECTORY", "/tmp/chord")

CHORD_AUTH_CONFIG_FILE = "auth_config.json"
CHORD_INSTANCE_CONFIG_FILE = "instance_config.json"

DEFAULT_INSTANCE_AUTH_FILE = Path(__file__).parent.absolute() / "instance_auth.json"


def get_instance_name(i: int):
    return f"chord{i}"


def get_instance_url(i: int):
    return f"http://{i}.chord.dlougheed.com/"  # Trailing slash important here


def action_build(args):
    subprocess.run((
        "sudo",
        "singularity",
        "build",
        *(("--remote",) if args.remote_build else ()),
        "chord.sif",
        "chord.def",
    ))


def action_build_docker(_args):
    subprocess.run(("docker", "build", "--no-cache", "."))


def action_shell(args):
    subprocess.run(("singularity", "shell", f"instance://{get_instance_name(args.node)}"))


def action_start(args):
    with open(args.instance_auth, "r") as f:
        instance_auth = json.load(f)

    for i in range(1, args.cluster_size + 1):
        instance_url = get_instance_url(i)
        if instance_url not in instance_auth:
            print(f"[CHORD DEV UTILS] Cannot find auth configuration for instance {instance_url}", file=sys.stderr)
            exit(1)

    for i in range(1, args.cluster_size + 1):
        print(f"[CHORD DEV UTILS] Starting instance {i}...")

        instance_data = os.path.join(CHORD_DATA_DIRECTORY, str(i))
        instance_temp = os.path.join(CHORD_TEMP_DIRECTORY, str(i))

        subprocess.run(("mkdir", "-p", instance_data, instance_temp))

        instance_url = get_instance_url(i)

        with open(os.path.join(instance_data, CHORD_INSTANCE_CONFIG_FILE), "w") as fc:
            json.dump({
                "CHORD_DEBUG": True,  # Whether the container is started in DEBUG mode
                "CHORD_PERMISSIONS": False,  # Whether the container uses the default permissions system
                "CHORD_PRIVATE_MODE": False,  # Whether the container will require authentication for everything

                "CHORD_URL": instance_url,
                "CHORD_REGISTRY_URL": get_instance_url(1),
            }, fc)

        with open(os.path.join(instance_data, CHORD_AUTH_CONFIG_FILE), "w") as fa:
            json.dump(instance_auth[instance_url], fa)

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


def action_restart(args):
    action_start(args)
    action_stop(args)


def action_update_web(args):
    subprocess.run(("singularity", "exec", f"instance://{get_instance_name(args.node)}",
                    "bash", "/chord/container_scripts/install_web.bash"))


ACTIONS = {
    "build": action_build,
    "build-docker": action_build_docker,
    "shell": action_shell,
    "start": action_start,
    "stop": action_stop,
    "restart": action_restart,
    "update-web": action_update_web,
}

ACTION_CHOICES = tuple(sorted(ACTIONS.keys()))


def main():
    parser = argparse.ArgumentParser(description="Helpers for CHORD server development.")
    parser.add_argument("--cluster-size", dest="cluster_size", type=int, default=1)
    parser.add_argument("--instance-auth", dest="instance_auth", type=lambda p: Path(p).absolute(),
                        default=DEFAULT_INSTANCE_AUTH_FILE, help="path/to/instance_auth.json")
    parser.add_argument("--node", dest="node", type=int, help="[node index]", default=1)
    parser.add_argument("--remote-build", dest="remote_build", action="store_true",
                        help="use Sylabs remote build service")
    parser.add_argument(
        "action",
        metavar="action",
        type=str,
        choices=ACTION_CHOICES,
        help="|".join(ACTION_CHOICES)
    )

    args = parser.parse_args()
    ACTIONS[args.action](args)


if __name__ == "__main__":
    main()
