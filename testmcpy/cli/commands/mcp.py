"""MCP profile management commands: profiles, status, explore-cli."""

import asyncio
import json

import typer
import yaml
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from testmcpy.cli.app import OutputFormat, app, console


@app.command()
def profiles(
    show_details: bool = typer.Option(
        False,
        "--details",
        "-d",
        help="Show detailed profile information",
    ),
    set_default: str = typer.Option(
        None,
        "--set-default",
        help="Set the default profile (writes to .mcp_services.yaml)",
    ),
    get_default: bool = typer.Option(
        False,
        "--get-default",
        help="Show the current default profile",
    ),
):
    """
    List and manage MCP profiles.

    View all configured MCP profiles, get/set the default profile.
    For interactive profile management, use: testmcpy dash

    Examples:
        testmcpy profiles                    # List all profiles
        testmcpy profiles --details          # Show detailed info
        testmcpy profiles --get-default      # Show default profile
        testmcpy profiles --set-default prod # Set 'prod' as default
    """
    from testmcpy.mcp_profiles import get_profile_config, load_profile

    profile_config = get_profile_config()

    # Handle --get-default
    if get_default:
        default = profile_config.default_profile
        if default:
            console.print(f"\n[bold cyan]Default MCP Profile:[/bold cyan] {default}\n")
        else:
            console.print("\n[yellow]No default profile set[/yellow]\n")
        return

    # Handle --set-default
    if set_default:
        # Verify profile exists
        if set_default not in profile_config.list_profiles():
            console.print(f"\n[red]Error: Profile '{set_default}' not found[/red]")
            console.print("\nAvailable profiles:")
            for p in profile_config.list_profiles():
                console.print(f"  • {p}")
            return

        # Read current YAML file
        config_path = profile_config.config_path
        if not config_path or not config_path.exists():
            console.print(f"\n[red]Error: Config file not found at {config_path}[/red]")
            console.print("Run: [cyan]testmcpy setup[/cyan]")
            return

        try:
            with open(config_path) as f:
                config_data = yaml.safe_load(f) or {}

            # Update default
            config_data["default"] = set_default

            # Write back
            with open(config_path, "w") as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

            console.print(f"\n[green]✓ Default profile set to:[/green] {set_default}")
            console.print(f"[dim]Updated: {config_path}[/dim]\n")

        except Exception as e:
            console.print(f"\n[red]Error updating config: {e}[/red]\n")
        return

    # List profiles
    console.print("\n[bold cyan]MCP Profiles[/bold cyan]\n")

    profile_ids = profile_config.list_profiles()

    if not profile_ids:
        console.print("[dim]No profiles configured.[/dim]")
        console.print("\nTo configure profiles, create [cyan].mcp_services.yaml[/cyan]")
        console.print(
            "See: [blue]https://github.com/preset-io/testmcpy/blob/main/docs/MCP_PROFILES.md[/blue]"
        )
        return

    # Get default profile
    default_profile_id = profile_config.default_profile

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("", style="dim", width=3)  # Default indicator
    table.add_column("Profile ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("MCPs", justify="right")
    if show_details:
        table.add_column("First MCP URL")
        table.add_column("Auth Type")

    for profile_id in profile_ids:
        profile = load_profile(profile_id)
        if not profile:
            continue

        is_default = profile_id == default_profile_id
        status_icon = "●" if is_default else "○"
        mcp_count = len(profile.mcps) if profile.mcps else 0

        row = [
            status_icon,
            profile_id,
            profile.name or "-",
            str(mcp_count),
        ]

        if show_details and profile.mcps:
            first_mcp = profile.mcps[0]
            row.extend(
                [
                    first_mcp.mcp_url,
                    first_mcp.auth.auth_type if first_mcp.auth else "none",
                ]
            )

        table.add_row(*row)

    console.print(table)
    console.print(f"\n[dim]Total: {len(profile_ids)} profile(s)[/dim]")
    if default_profile_id:
        console.print(f"[dim]Default: {default_profile_id}[/dim]")

    console.print("\n[bold]Commands:[/bold]")
    console.print("  [cyan]testmcpy profiles --get-default[/cyan]        # Show default profile")
    console.print("  [cyan]testmcpy profiles --set-default <name>[/cyan] # Set default profile")
    console.print("  [cyan]testmcpy dash[/cyan]                         # Interactive management")


@app.command()
def status(
    profile: str = typer.Option(
        None,
        "--profile",
        "-p",
        help="MCP profile to check",
    ),
):
    """
    Show MCP connection status (CLI parity command).

    Quick command to check MCP service connectivity without launching the TUI.
    For real-time status monitoring, use: testmcpy dash --auto-refresh
    """
    from testmcpy.mcp_profiles import get_profile_config, list_available_profiles

    console.print("\n[bold cyan]MCP Connection Status[/bold cyan]\n")

    # Get profile configuration
    profile_config = get_profile_config()

    if not profile_config.has_profiles():
        console.print("[red]No MCP profiles configured.[/red]")
        console.print("\nRun: [cyan]testmcpy setup[/cyan]")
        return

    # Determine which profiles to check
    if profile:
        profiles_to_check = [profile_config.get_profile(profile)]
        if not profiles_to_check[0]:
            console.print(f"[red]Profile '{profile}' not found.[/red]")
            return
    else:
        profiles_to_check = list_available_profiles()

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Profile", style="cyan")
    table.add_column("MCP Service")
    table.add_column("Status", justify="center")
    table.add_column("Tools", justify="right")

    async def check_profile_status(prof):
        """Check status of a single profile."""
        if not prof.mcps:
            return [(prof.profile_id, "N/A", "[red]No MCPs configured[/red]", "0")]

        results = []
        for mcp in prof.mcps:
            try:
                from testmcpy.src.mcp_client import MCPClient

                client = MCPClient(mcp.mcp_url)
                await client.initialize()
                tools = await client.list_tools()
                await client.close()

                status = "[green]🟢 Connected[/green]"
                tool_count = str(len(tools))
            except Exception:
                status = "[red]🔴 Error[/red]"
                tool_count = "0"

            results.append(
                (
                    prof.profile_id,
                    mcp.name,
                    status,
                    tool_count,
                )
            )

        return results

    # Check all profiles
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Checking connections...", total=len(profiles_to_check))

        for prof in profiles_to_check:
            try:
                results = asyncio.run(check_profile_status(prof))
                for row in results:
                    table.add_row(*row)
            except Exception as e:
                table.add_row(
                    prof.profile_id,
                    "Error",
                    f"[red]Failed: {str(e)[:30]}[/red]",
                    "0",
                )
            progress.advance(task)

    console.print(table)
    console.print("\nFor live monitoring: [cyan]testmcpy dash --auto-refresh[/cyan]")


@app.command(name="explore-cli")
def explore_cli(
    profile: str = typer.Option(
        None,
        "--profile",
        "-p",
        help="MCP profile to use",
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.table,
        "--output",
        "-o",
        help="Output format",
    ),
):
    """
    List available MCP tools (CLI parity command).

    Quick command to browse MCP tools without launching the TUI.
    For interactive exploration, use: testmcpy explorer (or testmcpy dash)
    """
    from testmcpy.mcp_profiles import get_profile_config

    console.print("\n[bold cyan]MCP Tools Explorer[/bold cyan]\n")

    # Get profile configuration
    profile_config = get_profile_config()

    if not profile_config.has_profiles():
        console.print("[red]No MCP profiles configured.[/red]")
        console.print("\nRun: [cyan]testmcpy setup[/cyan]")
        return

    # Get profile
    prof = profile_config.get_profile(profile)
    if not prof:
        console.print(f"[red]Profile '{profile}' not found.[/red]")
        return

    if not prof.mcps:
        console.print("[red]No MCP services configured in profile.[/red]")
        return

    async def fetch_tools():
        """Fetch tools from MCP service."""
        mcp = prof.mcps[0]
        try:
            from testmcpy.src.mcp_client import MCPClient

            auth_dict = mcp.auth.to_dict() if mcp.auth else None
            with console.status(f"[dim]Connecting to {mcp.name}...[/dim]"):
                client = MCPClient(mcp.mcp_url, auth=auth_dict)
                await client.initialize()
                tools = await client.list_tools()
                await client.close()

            return tools
        except Exception as e:
            console.print(f"[red]Error connecting to MCP:[/red] {e}")
            return []

    tools = asyncio.run(fetch_tools())

    if not tools:
        console.print("[yellow]No tools found.[/yellow]")
        return

    # Output based on format
    if output == OutputFormat.table:
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Tool Name", style="cyan")
        table.add_column("Description")

        for i, tool in enumerate(tools, 1):
            desc = tool.description if hasattr(tool, "description") else ""
            table.add_row(
                str(i),
                tool.name if hasattr(tool, "name") else "unknown",
                desc[:80] + ("..." if len(desc) > 80 else ""),
            )

        console.print(table)
        console.print(f"\n[dim]Total: {len(tools)} tool(s)[/dim]")

    elif output == OutputFormat.json:
        output_data = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
            }
            for tool in tools
        ]
        console.print(json.dumps(output_data, indent=2))

    elif output == OutputFormat.yaml:
        output_data = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
            }
            for tool in tools
        ]
        console.print(yaml.dump(output_data, default_flow_style=False))

    console.print("\nFor interactive exploration: [cyan]testmcpy explorer[/cyan]")
