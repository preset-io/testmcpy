"""Tool listing and export commands: tools, export."""

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from testmcpy.cli.app import DEFAULT_MCP_URL, OutputFormat, app, console


@app.command()
def tools(
    mcp_url: Optional[str] = typer.Option(
        None, "--mcp-url", help="MCP service URL (overrides profile)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", help="MCP service profile from .mcp_services.yaml"
    ),
    format: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format"),
    detail: bool = typer.Option(False, "--detail", "-d", help="Show detailed parameter schemas"),
    filter: Optional[str] = typer.Option(None, "--filter", help="Filter tools by name"),
):
    """
    List available MCP tools with beautiful formatting.

    This command connects to the MCP service and displays all available tools
    with their descriptions and parameter schemas in a readable format.
    """
    # Load config with profile if specified, or use default profile
    from testmcpy.mcp_profiles import get_profile_config

    profile_config = get_profile_config()
    effective_mcp_url = mcp_url
    auth_config = None
    effective_profile = profile

    # Get profile - either specified or default
    if profile:
        prof = profile_config.get_profile(profile)
    else:
        # Use default profile if available
        default_profile_id = profile_config.default_profile
        if default_profile_id:
            prof = profile_config.get_profile(default_profile_id)
            effective_profile = default_profile_id
        else:
            prof = None

    # Extract MCP URL and auth from profile
    if prof and prof.mcps:
        mcp_server = prof.mcps[0]
        effective_mcp_url = mcp_url or mcp_server.mcp_url
        auth_config = mcp_server.auth.to_dict() if mcp_server.auth else None
    else:
        effective_mcp_url = mcp_url or DEFAULT_MCP_URL

    async def list_tools():
        from testmcpy.src.mcp_client import MCPClient

        console.print(
            Panel.fit(
                f"[bold cyan]MCP Tools Explorer[/bold cyan]\n"
                f"Service: {effective_mcp_url}\n"
                f"Profile: {effective_profile or 'none'}\n"
                f"Auth: {auth_config.get('type', 'none') if auth_config else 'none'}",
                border_style="cyan",
            )
        )

        try:
            with console.status("[bold green]Connecting to MCP service...[/bold green]"):
                async with MCPClient(effective_mcp_url, auth=auth_config) as client:
                    all_tools = await client.list_tools()

                    # Apply filter if provided
                    if filter:
                        tools_list = [t for t in all_tools if filter.lower() in t.name.lower()]
                        if not tools_list:
                            console.print(f"[yellow]No tools found matching '{filter}'[/yellow]")
                            return
                    else:
                        tools_list = all_tools

                    if format == OutputFormat.table:
                        if detail:
                            # Detailed view with individual panels for each tool
                            for i, tool in enumerate(tools_list, 1):
                                # Create a panel for each tool
                                tool_content = []

                                # Description
                                tool_content.append("[bold]Description:[/bold]")
                                desc_lines = tool.description.split("\n")
                                for line in desc_lines[:5]:  # First 5 lines
                                    if line.strip():
                                        tool_content.append(f"  {line.strip()}")
                                if len(desc_lines) > 5:
                                    tool_content.append(
                                        f"  [dim]... and {len(desc_lines) - 5} more lines[/dim]"
                                    )

                                tool_content.append("")

                                # Input Parameters
                                if tool.input_schema:
                                    tool_content.append("[bold]Input Parameters:[/bold]")
                                    props = tool.input_schema.get("properties", {})
                                    required = tool.input_schema.get("required", [])

                                    if props:
                                        for param_name, param_info in props.items():
                                            param_type = param_info.get("type", "any")
                                            param_desc = param_info.get("description", "")
                                            is_required = "✓" if param_name in required else " "

                                            tool_content.append(
                                                f"  [{is_required}] [cyan]{param_name}[/cyan]: [yellow]{param_type}[/yellow]"
                                            )
                                            if param_desc:
                                                # Wrap long descriptions
                                                if len(param_desc) > 60:
                                                    param_desc = param_desc[:60] + "..."
                                                tool_content.append(
                                                    f"      [dim]{param_desc}[/dim]"
                                                )
                                    else:
                                        tool_content.append("  [dim]No parameters required[/dim]")
                                else:
                                    tool_content.append("[dim]No input schema[/dim]")

                                # Output Schema
                                tool_content.append("")
                                if tool.output_schema:
                                    tool_content.append("[bold]Output Schema:[/bold]")
                                    out_props = tool.output_schema.get("properties", {})
                                    out_type = tool.output_schema.get("type", "object")

                                    if out_props:
                                        for prop_name, prop_info in out_props.items():
                                            prop_type = prop_info.get("type", "any")
                                            prop_desc = prop_info.get("description", "")

                                            tool_content.append(
                                                f"  [cyan]{prop_name}[/cyan]: [yellow]{prop_type}[/yellow]"
                                            )
                                            if prop_desc:
                                                if len(prop_desc) > 60:
                                                    prop_desc = prop_desc[:60] + "..."
                                                tool_content.append(f"      [dim]{prop_desc}[/dim]")
                                    else:
                                        tool_content.append(f"  [dim]Returns: {out_type}[/dim]")
                                else:
                                    tool_content.append("[bold]Output Schema:[/bold]")
                                    tool_content.append("  [dim]Not specified[/dim]")

                                panel = Panel(
                                    "\n".join(tool_content),
                                    title=f"[bold green]{i}. {tool.name}[/bold green]",
                                    border_style="green",
                                    expand=False,
                                )
                                console.print(panel)
                                console.print()  # Spacing between tools
                        else:
                            # Compact table view
                            table = Table(
                                show_header=True,
                                header_style="bold cyan",
                                border_style="blue",
                                title=f"[bold]Available MCP Tools ({len(tools_list)})[/bold]",
                                title_style="bold magenta",
                            )
                            table.add_column("#", style="dim", width=4)
                            table.add_column("Tool Name", style="bold green", no_wrap=True)
                            table.add_column("Description", style="white")
                            table.add_column("Params", justify="center", style="cyan")

                            for i, tool in enumerate(tools_list, 1):
                                # Truncate description intelligently
                                desc = tool.description
                                if len(desc) > 80:
                                    # Try to cut at sentence or word boundary
                                    desc = desc[:80].rsplit(". ", 1)[0] + "..."

                                # Count parameters
                                param_count = (
                                    len(tool.input_schema.get("properties", {}))
                                    if tool.input_schema
                                    else 0
                                )
                                required_count = (
                                    len(tool.input_schema.get("required", []))
                                    if tool.input_schema
                                    else 0
                                )

                                param_str = f"{param_count}"
                                if required_count > 0:
                                    param_str = f"{param_count} ({required_count} req)"

                                table.add_row(str(i), tool.name, desc, param_str)

                            console.print(table)

                    elif format == OutputFormat.json:
                        output_data = [
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.input_schema,
                                "output_schema": tool.output_schema,
                            }
                            for tool in tools_list
                        ]
                        console.print(
                            Syntax(json.dumps(output_data, indent=2), "json", theme="monokai")
                        )

                    elif format == OutputFormat.yaml:
                        output_data = [
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.input_schema,
                                "output_schema": tool.output_schema,
                            }
                            for tool in tools_list
                        ]
                        console.print(Syntax(yaml.dump(output_data), "yaml", theme="monokai"))

                    # Summary
                    summary_parts = []
                    summary_parts.append(f"[green]{len(tools_list)} tool(s) displayed[/green]")
                    if filter:
                        summary_parts.append(
                            f"[yellow]filtered from {len(all_tools)} total[/yellow]"
                        )

                    console.print(f"\n[bold]Summary:[/bold] {' | '.join(summary_parts)}")

                    if not detail and format == OutputFormat.table:
                        console.print(
                            "[dim]Tip: Use --detail flag to see full parameter schemas[/dim]"
                        )

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error connecting to MCP service:[/red]\n{str(e)}",
                    title="[red]Error[/red]",
                    border_style="red",
                )
            )

    asyncio.run(list_tools())


@app.command()
def export(
    tool_name: Optional[str] = typer.Argument(None, help="Tool name to export (or use --all)"),
    format: str = typer.Option("typescript", "--format", "-f", help="Export format"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file"),
    all: bool = typer.Option(False, "--all", help="Export all tools"),
    profile: Optional[str] = typer.Option(None, "--profile", help="MCP profile"),
    mcp_url: Optional[str] = typer.Option(None, "--mcp-url", help="MCP service URL"),
):
    """
    Export MCP tool schemas in various formats.

    Supported formats: typescript, python, protobuf, thrift, graphql, curl, json, yaml

    Examples:
        # Export as TypeScript
        testmcpy export get_chart_data --format typescript

        # Export all tools as Python to file
        testmcpy export --all --format python -o schemas.py

        # Generate cURL command
        testmcpy export list_datasets --format curl

        # Use specific profile
        testmcpy export search --format protobuf --profile production
    """
    from testmcpy.formatters import FORMATS
    from testmcpy.mcp_profiles import get_profile_config

    # Load config with profile if specified, or use default profile
    profile_config = get_profile_config()
    effective_mcp_url = mcp_url
    auth_config = None

    # Get profile - either specified or default
    if profile:
        prof = profile_config.get_profile(profile)
    else:
        # Use default profile if available
        default_profile_id = profile_config.default_profile
        if default_profile_id:
            prof = profile_config.get_profile(default_profile_id)
        else:
            prof = None

    # Extract MCP URL and auth from profile
    if prof and prof.mcps:
        mcp_server = prof.mcps[0]
        effective_mcp_url = mcp_url or mcp_server.mcp_url
        auth_config = mcp_server.auth.to_dict() if mcp_server.auth else None
    else:
        effective_mcp_url = mcp_url or DEFAULT_MCP_URL

    # Validate format
    if format not in FORMATS:
        console.print(f"[red]Error: Unknown format '{format}'[/red]")
        console.print(f"[yellow]Supported formats: {', '.join(FORMATS.keys())}[/yellow]")
        raise typer.Exit(1)

    # Validate that either tool_name or --all is provided
    if not tool_name and not all:
        console.print("[red]Error: Either specify a tool name or use --all flag[/red]")
        console.print("[yellow]Example: testmcpy export my_tool --format typescript[/yellow]")
        raise typer.Exit(1)

    async def export_schemas():
        from testmcpy.src.mcp_client import MCPClient

        console.print(
            Panel.fit(
                f"[bold cyan]Export MCP Tool Schemas[/bold cyan]\n"
                f"Format: {FORMATS[format]['label']} | Service: {effective_mcp_url}",
                border_style="cyan",
            )
        )

        try:
            with console.status("[bold green]Connecting to MCP service...[/bold green]"):
                async with MCPClient(effective_mcp_url, auth=auth_config) as client:
                    tools_list = await client.list_tools()

                    if not tools_list:
                        console.print("[yellow]No tools found in MCP service[/yellow]")
                        return

                    # Filter tools if specific tool requested
                    if not all:
                        tools_list = [t for t in tools_list if t.name == tool_name]
                        if not tools_list:
                            console.print(f"[red]Error: Tool '{tool_name}' not found[/red]")
                            console.print(
                                f"[yellow]Available tools: {', '.join([t.name for t in await client.list_tools()])}[/yellow]"
                            )
                            return

                    console.print(f"[green]✓ Found {len(tools_list)} tool(s) to export[/green]\n")

                    # Get the conversion function
                    convert_func = FORMATS[format]["convert"]
                    language = FORMATS[format]["language"]

                    # Generate output
                    output_lines = []

                    for i, tool in enumerate(tools_list):
                        # Add separator between tools when exporting all
                        if all and i > 0:
                            if format in ["typescript", "python"]:
                                output_lines.append("\n\n")
                            elif format in ["protobuf", "thrift", "graphql"]:
                                output_lines.append("\n")
                            elif format == "curl":
                                output_lines.append("\n" + "=" * 80 + "\n\n")
                            else:
                                output_lines.append("\n---\n\n")

                        # Add tool name comment for clarity when exporting all
                        if all:
                            if format in ["typescript", "python", "protobuf", "thrift", "graphql"]:
                                output_lines.append(f"// Tool: {tool.name}\n")
                            elif format == "yaml":
                                output_lines.append(f"# Tool: {tool.name}\n")

                        # Convert schema
                        if format == "curl":
                            converted = convert_func(tool.input_schema, tool.name)
                        elif format in ["json", "yaml"]:
                            # For JSON/YAML, include tool metadata
                            schema_with_metadata = {
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.input_schema,
                                "output_schema": tool.output_schema,
                            }
                            converted = convert_func(schema_with_metadata)
                        else:
                            # For code formats, use a nice name
                            name = "".join(
                                word.capitalize() for word in tool.name.replace("-", "_").split("_")
                            )
                            if format == "typescript":
                                name = f"{name}Params"
                            elif format == "python":
                                name = f"{name}Params"
                            elif format == "protobuf":
                                name = f"{name}Request"
                            elif format == "thrift":
                                name = f"{name}Request"
                            elif format == "graphql":
                                name = f"{name}Input"

                            converted = convert_func(tool.input_schema, name)

                        output_lines.append(converted)

                    output_text = "".join(output_lines)

                    # Display or save output
                    if output:
                        output.write_text(output_text)
                        console.print(f"[green]✓ Exported to {output}[/green]")
                    else:
                        # Display with syntax highlighting
                        console.print(Syntax(output_text, language, theme="monokai"))

        except Exception as e:
            console.print(
                Panel(
                    f"[red]Error exporting schemas:[/red]\n{str(e)}",
                    title="[red]Error[/red]",
                    border_style="red",
                )
            )

    asyncio.run(export_schemas())
