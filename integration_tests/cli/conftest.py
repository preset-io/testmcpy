"""CLI integration test fixtures."""

import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner():
    """Create a Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def cli_app():
    """Import and return the testmcpy CLI app."""
    from testmcpy.cli import app

    return app
