# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

try:
    long_description = open("README.md").read()
except IOError:
    long_description = ""

setup(
    name="neptyne",
    version="0.1.0",
    description="Jupyter support for the kakoune editor",
    license="MIT",
    author="Dan Rosén",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'neptyne = neptyne:main',
            'wss = wss:main',
        ]
    },
    py_modules=["neptyne", "wss"],
    install_requires=[],
    long_description=long_description,
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.7",
    ]
)
