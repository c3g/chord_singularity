#!/usr/bin/env python

import setuptools

setuptools.setup(
    name="chord_container_tools",
    version="0.0.0",

    python_requires=">=3.6",
    install_requires=["jsonschema>=3.2,<4.0", "uWSGI>=2.0,<2.1"],

    author="David Lougheed",
    author_email="david.lougheed@mail.mcgill.ca",

    description="Unpublished package for setting up Bento Platform containers",

    packages=["chord_container_tools"],
    entry_points={
        "console_scripts": [
            "chord_container_setup = chord_container_tools.container_setup:job.main",
            "chord_container_pre_start = chord_container_tools.container_pre_start:job.main",
            "chord_container_post_start = chord_container_tools.container_post_start:job.main",
            "chord_container_post_stop = chord_container_tools.container_post_stop:job.main",
            "chord_container_non_wsgi_start = chord_container_tools.container_non_wsgi_start:job.main",
            "chord_container_non_wsgi_stop = chord_container_tools.container_non_wsgi_stop:job.main",
        ]
    },

    license="LGPLv3",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)",
        "Operating System :: POSIX :: Linux"
    ]
)
