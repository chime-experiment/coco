"""
coco metric module.

Helper functions for prometheus metric exporting.
"""

import re


def format_metric_label(name):
    match = re.search(r"(http:\/\/)?([A-Za-z0-9_]*):?([0-9]*)?", name.replace("-", "_"))
    return match[2], match[3].strip("/").strip()


def format_metric_name(name):
    return name.replace("-", "_").strip()
