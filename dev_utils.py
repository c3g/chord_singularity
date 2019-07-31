#!/usr/bin/env python3

import argparse
import os
import subprocess


def main():
    parser = argparse.ArgumentParser(description="Helpers for CHORD server development.")
    parser.add_argument("--cluster-size", dest="cluster_size", type=int, default=1)
    parser.add_argument("action", metavar="action", type=str, choices=["build", "start", "stop"],
                        help="build|start|stop")
    args = parser.parse_args()

    if args.action == "build":
        subprocess.run(["sudo", "singularity", "build", "chord.sif", "chord.def"])

    elif args.action == "start":
        for i in range(1, args.cluster_size + 1):
            print(f"[CHORD DEV UTILS] Starting instance {i}...")
            with open(f"/tmp/chord/{i}/env", "w") as f:
                f.write(f"CHORD_URL=http://{i}.chord.dlougheed.com/\n")

            user_dir = os.path.expanduser("~")
            subprocess.run(["mkdir", "-p", f"/tmp/chord/{i}"])
            subprocess.run(["mkdir", "-p", os.path.join(user_dir, f"chord_data/{i}")])
            subprocess.run(["singularity", "instance", "start",
                            "--bind", f"/tmp/chord/{i}:/chord/tmp",
                            "--bind", os.path.join(user_dir, f"chord_data/{i}") + ":/chord/data",
                            "chord.sif", f"chord{i}"])

    elif args.action == "stop":
        for i in range(1, args.cluster_size + 1):
            print(f"[CHORD DEV UTILS] Stopping instance {i}...")
            subprocess.run(["singularity", "instance", "stop", f"chord{i}"])


if __name__ == "__main__":
    main()