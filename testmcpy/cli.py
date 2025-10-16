#!/usr/bin/env python3
"""
MCP Testing Framework CLI - Test and validate LLM+MCP interactions.

This CLI provides commands for testing LLM tool calling capabilities with MCP services,
running evaluation suites, and generating reports.
"""

import asyncio
import json
import os
import logging
from pathlib import Path
from typing import Optional, List
from enum import Enum

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.syntax import Syntax
from rich import print as rprint
import yaml
from dotenv import load_dotenv

# Suppress MCP notification validation warnings
logging.getLogger().setLevel(logging.ERROR)

# Load environment variables from .env file
load_dotenv(Path(__file__).parent.parent / ".env")

app = typer.Typer(
    name="testmcpy",
    help="MCP Testing Framework - Test LLM tool calling with MCP services",
    add_completion=False,
)

console = Console()

# Config defaults from environment variables
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama3.1:8b")
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "ollama")
DEFAULT_MCP_URL = os.getenv("MCP_URL", "http://localhost:5008/mcp/")


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


@app.command()
def tools(
    mcp_url: str = typer.Option(DEFAULT_MCP_URL, "--mcp-url", help="MCP service URL"),
    format: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format"),
    detail: bool = typer.Option(False, "--detail", "-d", help="Show detailed parameter schemas"),
    filter: Optional[str] = typer.Option(None, "--filter", help="Filter tools by name"),
):
    """
    List available MCP tools with beautiful formatting.

    This command connects to the MCP service and displays all available tools
    with their descriptions and parameter schemas in a readable format.
    """
    async def list_tools():
        from testmcpy.src.mcp_client import MCPClient

        console.print(Panel.fit(
            f"[bold cyan]MCP Tools Explorer[/bold cyan]\n"
            f"Service: {mcp_url}",
            border_style="cyan"
        ))

        try:
            with console.status("[bold green]Connecting to MCP service...[/bold green]"):
                async with MCPClient(mcp_url) as client:
                    all_tools = await client.list_tools()

                    # Apply filter if provided
                    if filter:
                        tools = [t for t in all_tools if filter.lower() in t.name.lower()]
                        if not tools:
                            console.print(f"[yellow]No tools found matching '{filter}'[/yellow]")
                            return
                    else:
                        tools = all_tools

                    if format == OutputFormat.table:
                        if detail:
                            # Detailed view with individual panels for each tool
                            for i, tool in enumerate(tools, 1):
                                # Create a panel for each tool
                                tool_content = []

                                # Description
                                tool_content.append(f"[bold]Description:[/bold]")
                                desc_lines = tool.description.split('\n')
                                for line in desc_lines[:5]:  # First 5 lines
                                    if line.strip():
                                        tool_content.append(f"  {line.strip()}")
                                if len(desc_lines) > 5:
                                    tool_content.append(f"  [dim]... and {len(desc_lines) - 5} more lines[/dim]")

                                tool_content.append("")

                                # Parameters
                                if tool.input_schema:
                                    tool_content.append(f"[bold]Parameters:[/bold]")
                                    props = tool.input_schema.get('properties', {})
                                    required = tool.input_schema.get('required', [])

                                    if props:
                                        for param_name, param_info in props.items():
                                            param_type = param_info.get('type', 'any')
                                            param_desc = param_info.get('description', '')
                                            is_required = '✓' if param_name in required else ' '

                                            tool_content.append(f"  [{is_required}] [cyan]{param_name}[/cyan]: [yellow]{param_type}[/yellow]")
                                            if param_desc:
                                                # Wrap long descriptions
                                                if len(param_desc) > 60:
                                                    param_desc = param_desc[:60] + "..."
                                                tool_content.append(f"      [dim]{param_desc}[/dim]")
                                    else:
                                        tool_content.append("  [dim]No parameters required[/dim]")
                                else:
                                    tool_content.append(f"[dim]No parameter schema[/dim]")

                                panel = Panel(
                                    "\n".join(tool_content),
                                    title=f"[bold green]{i}. {tool.name}[/bold green]",
                                    border_style="green",
                                    expand=False
                                )
                                console.print(panel)
                                console.print()  # Spacing between tools
                        else:
                            # Compact table view
                            table = Table(
                                show_header=True,
                                header_style="bold cyan",
                                border_style="blue",
                                title=f"[bold]Available MCP Tools ({len(tools)})[/bold]",
                                title_style="bold magenta"
                            )
                            table.add_column("#", style="dim", width=4)
                            table.add_column("Tool Name", style="bold green", no_wrap=True)
                            table.add_column("Description", style="white")
                            table.add_column("Params", justify="center", style="cyan")

                            for i, tool in enumerate(tools, 1):
                                # Truncate description intelligently
                                desc = tool.description
                                if len(desc) > 80:
                                    # Try to cut at sentence or word boundary
                                    desc = desc[:80].rsplit('. ', 1)[0] + "..."

                                # Count parameters
                                param_count = len(tool.input_schema.get('properties', {})) if tool.input_schema else 0
                                required_count = len(tool.input_schema.get('required', [])) if tool.input_schema else 0

                                param_str = f"{param_count}"
                                if required_count > 0:
                                    param_str = f"{param_count} ({required_count} req)"

                                table.add_row(
                                    str(i),
                                    tool.name,
                                    desc,
                                    param_str
                                )

                            console.print(table)

                    elif format == OutputFormat.json:
                        output_data = [
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.input_schema
                            }
                            for tool in tools
                        ]
                        console.print(Syntax(json.dumps(output_data, indent=2), "json", theme="monokai"))

                    elif format == OutputFormat.yaml:
                        output_data = [
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.input_schema
                            }
                            for tool in tools
                        ]
                        console.print(Syntax(yaml.dump(output_data), "yaml", theme="monokai"))

                    # Summary
                    summary_parts = []
                    summary_parts.append(f"[green]{len(tools)} tool(s) displayed[/green]")
                    if filter:
                        summary_parts.append(f"[yellow]filtered from {len(all_tools)} total[/yellow]")

                    console.print(f"\n[bold]Summary:[/bold] {' | '.join(summary_parts)}")

                    if not detail and format == OutputFormat.table:
                        console.print("[dim]Tip: Use --detail flag to see full parameter schemas[/dim]")

        except Exception as e:
            console.print(Panel(
                f"[red]Error connecting to MCP service:[/red]\n{str(e)}",
                title="[red]Error[/red]",
                border_style="red"
            ))

    asyncio.run(list_tools())


if __name__ == "__main__":
    app()
