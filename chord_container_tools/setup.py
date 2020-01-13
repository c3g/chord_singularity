#!/usr/bin/env python

import setuptools

setuptools.setup(
    name="chord_container_tools",
    version="0.0.0",

    python_requires=">=3.6",
    install_requires=["jsonschema>=3.2,<4.0", "uWSGI>=2.0,<2.1"],

    author="David Lougheed",
    author_email="david.lougheed@mail.mcgill.ca",

    description="Unpublished package for setting up CHORD containers",

    packages=["chord_container_tools"],
    entry_points={
        "console_scripts": [
            "chord_container_setup = chord_container_tools.container_setup:main",
            "chord_container_pre_start = chord_container_tools.container_pre_start:entry",
            "chord_container_post_stop = chord_container_tools.container_post_stop:entry",
            "chord_container_non_wsgi_start = chord_container_tools.container_non_wsgi_start:entry",
            "chord_container_non_wsgi_stop = chord_container_tools.container_non_wsgi_stop:entry",
        ]
    },

    license="LGPLv3",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)",
        "Operating System :: POSIX :: Linux"
    ]
)
