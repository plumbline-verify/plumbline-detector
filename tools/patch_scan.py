"""Moved to plumbline_detector.patch_rules (unchanged); re-exported here so
the studies that import tools/patch_scan keep running identical code."""

from plumbline_detector.patch_rules import *  # noqa: F401,F403
from plumbline_detector.patch_rules import _code_part, _in_string, _lines  # noqa: F401
