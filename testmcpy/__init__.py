"""
testmcpy - MCP Testing Framework

A comprehensive testing framework for validating LLM tool calling
capabilities with MCP (Model Context Protocol) services.
"""

import warnings


def _silence_authlib_jose_deprecation() -> None:
    """Suppress the ``authlib.jose module is deprecated`` warning that fastmcp's
    JWT verifier triggers transitively (``fastmcp.server.auth.providers.jwt``
    imports ``authlib.jose``). It's a third-party migration notice we can't act
    on from here, and it clutters every CLI and test run that touches MCP auth.

    ``authlib.deprecate`` installs its own ``simplefilter("always", ...)`` at
    import time, which sits at the front of the filter list and overrides any
    ignore we register earlier. So import that submodule first (it only defines
    the warning + filter — it does NOT emit anything; only ``authlib.jose``
    does), then register our ignore ahead of it, before ``authlib.jose`` is
    imported anywhere. This module is the testmcpy package root, so it runs
    before any ``testmcpy.*`` submodule pulls in fastmcp.
    """
    try:
        import authlib.deprecate  # noqa: F401  (import for its side-effecting filter)
    except ImportError:
        # authlib not installed (fastmcp absent) — nothing emits the warning.
        return
    warnings.filterwarnings(
        "ignore",
        message=r"authlib\.jose module is deprecated",
        category=DeprecationWarning,
    )


_silence_authlib_jose_deprecation()

from importlib.metadata import PackageNotFoundError, version  # noqa: E402

try:
    __version__ = version("testmcpy")
except PackageNotFoundError:
    # Running from a bare checkout without an installed package — use an
    # obviously-not-a-release marker instead of a stale hardcoded version.
    __version__ = "0.0.0+unknown"

__author__ = "testmcpy Contributors"
