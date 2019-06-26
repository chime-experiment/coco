.. coco documentation master file, created by
   sphinx-quickstart on Wed Apr 10 18:28:30 2019.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

coco
================================

coco keeps a number of hosts organized in groups.
Using YAML files endpoints can be defined to be exposed or called on specified conditions. The call
of an endpoint results in coco calling the same endpoint on a given set of hosts. coco can be
configured to check or compare the results and based on that export prometheus alerts, write slack
messages or call other endpoints.
The values passed to endpoints can be marked as part of a global state, which is tracked and kept
in sync on the hosts.


.. toctree::
   :caption: Configuration:
   :maxdepth: 2

   endpoint

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
