"""Compatibility adapter for the independently installable headless probe.

Applications already depending on testmcpy should import this module. Minimal
CI consumers may depend directly on :mod:`testmcpy_oauth_probe`.
"""

from testmcpy_oauth_probe import *  # noqa: F403
from testmcpy_oauth_probe import __all__  # noqa: F401
