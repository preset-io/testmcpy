"""CLI package for testmcpy."""

from testmcpy.cli.app import app, console

# Import command modules to register their commands with the app
from testmcpy.cli.commands import (
    agent,  # noqa: F401
    baseline,  # noqa: F401
    export_db,  # noqa: F401
    mcp,  # noqa: F401
    metamorphic,  # noqa: F401
    multi_env,  # noqa: F401
    mutate,  # noqa: F401
    push,  # noqa: F401
    run,  # noqa: F401
    server,  # noqa: F401
    tools,  # noqa: F401
    tui,  # noqa: F401
    wizard,  # noqa: F401
)

__all__ = ["app", "console"]
