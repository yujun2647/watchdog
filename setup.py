#!/usr/bin/env python

from setuptools import setup
from watch_dog import __version__

with open("README.md", "r") as fp:
    README = fp.read()


def _get_requires(filename):
    with open(filename, "r") as fp:
        lines = fp.readlines()
        return [l.replace("\n", "") for l in lines if not l.startswith("#")]


INSTALL_REQUIRES = _get_requires("requirements.txt")

setup(
    name="watch_dog",
    version=__version__,
    description="",
    install_requires=INSTALL_REQUIRES,
    url="",
    author="walkerjun",
    author_email="yujun2647@163.com",
    download_url="",

    entry_points={
        "console_scripts": [
            "watchdog=watch_dog:watch",
        ],
    },
    packages=["watch_dog"],
    long_description=README,
)
