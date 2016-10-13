#!/usr/bin/env python
from setuptools import setup, find_packages

# Root package meta-data
# ----------------------
_name = 'ansible-mikrotik-utils'
_version = '0.0.3'
_keywords = ['mikrotik', 'ansible', 'configuration']

# Pwackages
# --------

_packages = find_packages('src', exclude=("tests", "tests.*"))
_package_dir = {'ansible_mikrotik_utils': 'src/ansible_mikrotik_utils'}

# Additional meta-data
# --------------------
_codename = 'mikroshit'
_release = '-'.join([_version, _codename])
_description = (
    """This module provides code that can parse exported configurations from
    Mikrotik devices, and create the script that represents the necessary
    commands to reach a target configuration.

    This code is used by the `mkr_config` Ansible module, so that it can
    idempotently manage the configuration of Mikrotik routers.
    """
)
_author = 'EDEN 3D Engineering'
_author_email = 'contact@eden-3d.org'
_url = 'https://github.com/eden3d/ansible-mikrotik-utils'
_download_url = 'https://github.com/eden3d/ansible-mikrotik-utils/zipball/master'
_copyright = '2016, EDEN 3D Engineering'
_licence = 'GNU General Public Licence V3.0'
_classifiers = [
    'Development Status :: 4 - Beta',
    ('License :: OSI Approved :: '
     'GNU General Public License v3 or later (GPLv3+)'),
    'Programming Language :: Python :: 2.7',
]

# Tests
# -----

_setup_requires = [
    'pytest-runner',
]
_tests_require = [
    'pytest',
    'pytest-cov',
]

# Package setup
# -------------

setup(
    name=_name,
    version=_version,
    keywords=_keywords,
    packages=_packages,
    package_dir=_package_dir,
    description=_description,
    author=_author,
    author_email=_author_email,
    url=_url,
    download_url=_download_url,
    license=_licence,
    classifiers=_classifiers,
    setup_requires=_setup_requires,
    tests_require=_tests_require,
)
