#!/usr/bin/python3
"""
coco, a config controller.

``coco`` lives on
`GitHub <https://github.com/chime-experiment/coco>`_.
"""

import setuptools
import versioneer


# Load the PEP508 formatted requirements from the requirements.txt file. Needs
# pip version > 19.0
with open("requirements.txt", "r") as fh:
    requires = fh.readlines()

# Now for the regular setuptools-y stuff
setuptools.setup(
    name="coco",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    author="The CHIME Collaboration",
    author_email="rick@phas.ubc.ca",
    description="A Config Controller",
    packages=["coco"],
    scripts=["scripts/coco", "scripts/coco-client"],
    license="GPL v3.0",
    url="http://github.com/chime-experiment/coco",
    install_requires=requires,
)
