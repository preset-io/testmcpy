"""Main CLI application setup and shared utilities."""

import warnings

# Suppress deprecation warnings before any other imports
warnings.filterwarnings("ignore", category=DeprecationWarning)

import logging  # noqa: E402
from enum import Enum  # noqa: E402
from pathlib import Path  # noqa: E402

import typer  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from rich.console import Console  # noqa: E402

from testmcpy import __version__  # noqa: E402
from testmcpy.config import get_config  # noqa: E402

# Suppress MCP notification validation warnings
logging.getLogger().setLevel(logging.ERROR)

# Load environment variables from .env file (for backward compatibility)
load_dotenv(Path(__file__).parent.parent.parent / ".env")

app = typer.Typer(
    name="testmcpy",
    help="MCP Testing Framework - Test LLM tool calling with MCP services",
    add_completion=False,
)

console = Console()


def print_logo():
    """Print testmcpy ASCII logo."""
    logo = """
  [bold cyan]▀█▀ █▀▀ █▀ ▀█▀ █▀▄▀█ █▀▀ █▀█ █▄█[/bold cyan]
  [bold cyan] █  ██▄ ▄█  █  █ ▀ █ █▄▄ █▀▀  █ [/bold cyan]

  [dim]🧪 Test  •  📊 Benchmark  •  ✓ Validate[/dim]
  [dim]MCP Testing Framework[/dim]
"""
    console.print(logo)


def version_callback(value: bool):
    """Display version and exit."""
    if value:
        print_logo()
        console.print(f"\n  Version: [green]{__version__}[/green]")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True,
    ),
):
    """
    testmcpy - MCP Testing Framework

    Test and validate LLM tool calling capabilities with MCP services.
    """
    pass


# Get config instance
config = get_config()

# Get defaults from LLM profile if available
_default_llm = config.get_default_llm_provider()
DEFAULT_MODEL = _default_llm.model if _default_llm else "claude-sonnet-4-5"
DEFAULT_PROVIDER = _default_llm.provider if _default_llm else "anthropic"

# Get default MCP URL from profile if available
_default_mcp_url = config.get_mcp_url()
DEFAULT_MCP_URL = _default_mcp_url if _default_mcp_url else None


class OutputFormat(str, Enum):
    """Output format options."""

    yaml = "yaml"
    json = "json"
    table = "table"


class ModelProvider(str, Enum):
    """Supported model providers."""

    ollama = "ollama"
    openai = "openai"
    local = "local"
    anthropic = "anthropic"
    claude_sdk = "claude-sdk"
    claude_cli = "claude-cli"
    claude_code = "claude-code"
