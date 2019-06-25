"""
coco metric module.

Exports metrics to prometheus.
"""

import re


def format_metric_label(name):
    match = re.search(r"(http:\/\/)?([A-Za-z0-9_]*)(:.*)?", name.replace('-', '_'))
    return match[2] + match[3].replace(':', '_').strip('/').strip()


def format_metric_name(name):
    return name.replace('-', '_').strip()
