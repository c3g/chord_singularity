#!/usr/bin/env python3

import argparse
import subprocess

from pathlib import Path

BENTO_FOLDER = Path(__file__).parent.absolute()

BENTO_SINGULARITY_TEMPLATE = BENTO_FOLDER / "bento.def.template"
BENTO_DOCKER_TEMPLATE = BENTO_FOLDER / "Dockerfile.template"

TEMPLATE_REPLACEMENTS = {
    "__BENTO_SERVICES_JSON_SCHEMA": (BENTO_FOLDER / "chord_services.schema.json").resolve(),
    "__BENTO_CONTAINER_SCRIPTS": (BENTO_FOLDER / "container_scripts").resolve(),
    "__BENTO_CONTAINER_TOOLS": (BENTO_FOLDER / "chord_container_tools").resolve(),
    "__BENTO_LICENSE": (BENTO_FOLDER / "LICENSE").resolve(),
    "__BENTO_README": (BENTO_FOLDER / "README.md").resolve(),
}

DEFAULT_BENTO_SERVICES_JSON = BENTO_FOLDER / "chord_services.json"


def _edit_template(file_path: str, bento_services_path: str):
    subprocess.run(("sed", "-i", f"s=__BENTO_SERVICES_JSON={bento_services_path}=g", file_path))
    for value, replacement in TEMPLATE_REPLACEMENTS.items():
        subprocess.run(("sed", "-i", f"s={value}={replacement}=g", file_path))


def action_build(args):
    subprocess.run(("cp", BENTO_SINGULARITY_TEMPLATE.resolve(), "./bento.def"))
    _edit_template("./bento.def", args.bento_services_json.resolve())
    subprocess.run((
        "sudo",
        "singularity",
        "build",
        *(("--remote",) if args.remote_build else ()),
        args.container_name,
        "bento.def",
    ))
    subprocess.run(("rm", "./bento.def"))


def action_build_docker(args):
    subprocess.run(("cp", BENTO_DOCKER_TEMPLATE.resolve(), "./Dockerfile"))
    _edit_template("./Dockerfile", args.bento_services_json.resolve())
    subprocess.run(("docker", "build", "--no-cache", "."))
    subprocess.run(("rm", "./Dockerfile"))


ACTIONS = {
    "build": action_build,
    "build-docker": action_build_docker,
}

ACTION_CHOICES = tuple(sorted(ACTIONS.keys()))


def main():
    parser = argparse.ArgumentParser(description="Helpers for Bento Platform container creation.")
    parser.add_argument("--remote-build", dest="remote_build", action="store_true",
                        help="use Sylabs remote build service for building Singularity container")
    parser.add_argument("--container-name", dest="container_name", type=str, help="[Singularity container file name]",
                        default="bento.sif")
    parser.add_argument("--bento-services-json", dest="bento_services_json", type=lambda p: Path(p).absolute(),
                        default=DEFAULT_BENTO_SERVICES_JSON, help="path/to/bento_services.json")
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
