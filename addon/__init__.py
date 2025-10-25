"""
Addon package for optional auto-patching capabilities.

Provides helper modules that can be imported by process_inspector
without making them mandatory for basic functionality.
"""

from . import auto_patch, patch_runner, utils

__all__ = ["auto_patch", "patch_runner", "utils"]
