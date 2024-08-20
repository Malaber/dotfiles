#!/usr/bin/env python
import os

username = os.environ['ARTIFACTORY_USER']
password = os.environ['ARTIFACTORY_TOKEN_BASE64']

pypirc_content = f"""
[distutils]
index-servers =
    pypi
    bit-local-debian-pypi

[bit-local-debian-pypi]
repository: https://artifactory.1and1.org/artifactory/api/pypi/bit-local-debian-pypi/simple
username: {username}
password: {password}
"""

with open(os.path.expanduser('~/.pypirc'), 'w') as f:
    f.write(pypirc_content.strip())
