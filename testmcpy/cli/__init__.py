"""CLI package for testmcpy."""

from testmcpy.cli.app import app, console

# Import command modules to register their commands with the app
from testmcpy.cli.commands import (
    mcp,  # noqa: F401
    run,  # noqa: F401
    server,  # noqa: F401
    tools,  # noqa: F401
    tui,  # noqa: F401
)

__all__ = ["app", "console"]
