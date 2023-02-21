#!/usr/bin/env python
import os

from setuptools import setup
from watch_dog import __version__

with open("README.md", "r") as fp:
    README = fp.read()


def _get_requires(filename):
    with open(filename, "r") as fp:
        lines = fp.readlines()
        return [l.replace("\n", "") for l in lines if not l.startswith("#")]


def walk_package(package):
    packages = []
    for name, folders, files in os.walk(package):
        folders = [f for f in folders if not f.startswith("__")]
        files = [f for f in files if not f.endswith(".pyc")]
        if "__init__.py" in files:
            packages.append(name)
            for folder in folders:
                sub_name = os.path.join(name, folder)
                _packages = walk_package(sub_name)
                packages.extend(_packages)

    return packages


all_packages = walk_package("watch_dog")
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
            "watchdog=watch_dog.watch:main",
        ],
    },
    packages=all_packages,
    package_data={
        "watch_dog": [
            "ai/object_detect/model_data/*",
            "static/*",
        ]
    },
    long_description=README,
)
