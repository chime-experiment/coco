#!/usr/bin/python3
"""
coco, a config controller.

``coco`` lives on
`GitHub <https://github.com/chime-experiment/coco>`_.
"""


import os
import setuptools
import shutil
import sys
import versioneer

# The path to install the endpoint configuration files into, if any
endpoint_dst = None

# Strip out a --endpoint-conf option if given to the install command
found_install = False
for arg in sys.argv:
    if arg == "install":
        found_install = True
    elif found_install and arg.startswith("--endpoint-conf="):
        endpoint_dst = os.path.join(arg[arg.find("=") + 1 :], "endpoints")
        sys.argv.remove(arg)
        break

# Installing endpoint configuration, if requested
if endpoint_dst:
    # Check for the source directory
    endpoint_src = os.path.join(os.path.dirname(sys.argv[0]), "conf", "endpoints")
    if not os.path.isdir(endpoint_src):
        raise FileExistsError(
            "Endpoint configaration directory {0} not found".format(endpoint_src)
        )

    # We don't allow installing the endpoint config directory over
    # top of an existing directory, because that would likely
    # result in a mix of old and new configuration
    try:
        os.mkdir(endpoint_dst, 0o755)
    except FileExistsError:
        # Re-raise with an explanation
        raise FileExistsError(
            "Cannot install endpoint configuration: " "{0} already exists.".format(endpoint_dst)
        )

    # Now copy all the endpoint configuration files
    print("Installing endpoint configuration files to {0}".format(endpoint_dst))
    for name in os.listdir(endpoint_src):
        path = os.path.join(endpoint_src, name)
        if name.endswith(".conf") and os.path.isfile(path):
            shutil.copy(path, endpoint_dst)

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
)
