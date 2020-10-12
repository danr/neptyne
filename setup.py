# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

try:
    long_description = open("README.md").read()
except IOError:
    long_description = ""

setup(
    name="neptyne",
    version="0.1.0",
    description="Lightweight jupyter sidekick",
    license="MIT",
    author="Dan Rosén",
    entry_points={
        'console_scripts': [
            'neptyne = neptyne:main',
        ]
    },
    py_modules=["neptyne"],
    packages=['.'],
    package_data={
        '.': ["*.js", "*.kak"],
    },
    install_requires=[ r for r in open("requirements.txt").read().split('\n') if not r.startswith('#') ],
    long_description=long_description,
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.7",
    ]
)
