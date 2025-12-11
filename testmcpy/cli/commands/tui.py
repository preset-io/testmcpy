"""TUI and interactive commands: dash, explore, chat, interact."""

import asyncio

import typer
from rich.panel import Panel

from testmcpy.cli.app import (
    DEFAULT_MCP_URL,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    ModelProvider,
    app,
    console,
)


@app.command()
def dash(
    profile: str = typer.Option(None, "--profile", "-p", help="MCP profile to use"),
    auto_refresh: bool = typer.Option(False, "--auto-refresh", help="Auto-refresh status"),
):
    """
    Launch interactive TUI dashboard.

    Beautiful terminal-based dashboard for MCP testing and exploration.
    Navigate with keyboard shortcuts, manage profiles, explore tools, and more.

    Features:
    - Browse MCP tools and resources
    - Manage profiles
    - View connection status
    - Quick actions and shortcuts

    Press '?' for help once inside the dashboard.
    """
    try:
        from testmcpy.tui.app import run_tui
    except ImportError:
        console.print("[red]Error: Textual is required for the TUI dashboard[/red]")
        console.print("Install with: pip install 'testmcpy[tui]' or pip install textual")
        console.print("Or upgrade: pip install --upgrade testmcpy")
        return

    # Launch the TUI
    try:
        run_tui(profile=profile, enable_auto_refresh=auto_refresh)
    except Exception as e:
        console.print(f"[red]Error launching dashboard:[/red] {e}")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")


@app.command()
def explore(
    profile: str | None = typer.Option(
        None, "--profile", "-p", help="MCP service profile from .mcp_services.yaml"
    ),
):
    """
    Launch interactive MCP explorer TUI.

    This command starts an interactive terminal interface for browsing and
    exploring MCP tools, resources, and prompts. Features include:

    - Browse tools organized by categories
    - View detailed tool documentation and schemas
    - Search and filter tools
    - Generate test files from tools
    - AI-powered documentation optimization

    Navigation:
    - Arrow keys / hjkl: Navigate tree
    - Enter: Expand/collapse or show details
    - /: Search tools
    - t: Generate test for selected tool
    - o: Optimize docs for selected tool
    - h / Esc: Return to home
    - q: Quit
    """
    console.print(
        Panel.fit(
            "[bold cyan]MCP Explorer - Interactive TUI[/bold cyan]\n"
            f"Profile: {profile or 'default'}",
            border_style="cyan",
        )
    )

    try:
        # Import here to avoid dependency issues if textual not installed
        from testmcpy.tui.simple_app import run_tui

        run_tui(profile=profile)
    except ImportError:
        console.print(
            "[red]Error: Textual is required for the TUI explorer[/red]\n"
            "Install with: pip install 'testmcpy[tui]' or pip install textual",
            markup=False,
        )
    except Exception as e:
        console.print(f"[red]Error launching explorer:[/red] {e}")


@app.command()
def chat(
    profile: str | None = typer.Option(None, "--profile", "-p", help="MCP profile to use"),
    provider: str | None = typer.Option(
        None, "--provider", help="LLM provider (anthropic, openai, ollama, etc.)"
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="Model name"),
    mcp_url: str | None = typer.Option(None, "--mcp-url", help="MCP service URL"),
):
    """
    Launch interactive chat interface with tool calling visualization.

    This opens a beautiful terminal UI for chatting with an LLM that has
    access to MCP tools. All tool calls are visualized in real-time, and
    you can save conversations as tests or evaluate them with evaluators.

    Key bindings:
    - Enter: Send message
    - Ctrl+E: Evaluate conversation
    - Ctrl+S: Save as test
    - Ctrl+C: Cancel/Exit

    Examples:
        testmcpy chat                          # Use default config
        testmcpy chat --profile prod           # Use specific MCP profile
        testmcpy chat --model claude-opus-4    # Use specific model
    """
    try:
        # Check if textual is installed
        try:
            from testmcpy.tui.app import launch_chat
        except ImportError:
            console.print(
                Panel(
                    "[red]Error:[/red] Textual not installed\n\n"
                    "The chat interface requires Textual. Install it with:\n"
                    "[cyan]pip install textual textual-dev[/cyan]",
                    title="[red]Missing Dependency[/red]",
                    border_style="red",
                )
            )
            raise typer.Exit(1)

        # Launch the chat interface
        launch_chat(
            profile=profile,
            provider=provider,
            model=model,
            mcp_url=mcp_url,
        )

    except KeyboardInterrupt:
        console.print("\n[dim]Chat session ended.[/dim]")
    except Exception as e:
        console.print(
            Panel(
                f"[red]Error launching chat:[/red]\n{str(e)}",
                title="[red]Error[/red]",
                border_style="red",
            )
        )
        raise typer.Exit(1)


@app.command()
def interact(
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Model to use"),
    provider: ModelProvider = typer.Option(
        DEFAULT_PROVIDER, "--provider", "-p", help="Model provider"
    ),
    mcp_url: str | None = typer.Option(
        None, "--mcp-url", help="MCP service URL (overrides profile)"
    ),
    profile: str | None = typer.Option(
        None, "--profile", help="MCP service profile from .mcp_services.yaml"
    ),
    no_mcp: bool = typer.Option(False, "--no-mcp", help="Interact without MCP tools"),
):
    """
    Interactive conversation with LLM that has access to MCP tools.

    Start an interactive session where you can directly talk to the LLM and it can use
    MCP tools from your service. Type 'exit' or 'quit' to end the session.

    Use --no-mcp flag to interact without MCP tools.
    """
    # Load config with profile if specified
    if profile:
        from testmcpy.config import Config

        cfg = Config(profile=profile)
        effective_mcp_url = mcp_url or cfg.get_mcp_url()
    else:
        effective_mcp_url = mcp_url or DEFAULT_MCP_URL

    if no_mcp:
        console.print(
            Panel.fit(
                f"[bold cyan]Interactive Session with {model}[/bold cyan]\n"
                f"Provider: {provider.value}\nMode: Standalone (no MCP tools)\n\n"
                "[dim]Type your message and press Enter. "
                "Type 'exit' or 'quit' to end session.[/dim]",
                border_style="cyan",
            )
        )
    else:
        console.print(
            Panel.fit(
                f"[bold cyan]Interactive Session with {model}[/bold cyan]\n"
                f"Provider: {provider.value}\nMCP Service: {effective_mcp_url}\n\n"
                "[dim]Type your message and press Enter. "
                "Type 'exit' or 'quit' to end session.[/dim]",
                border_style="cyan",
            )
        )

    async def interact_session():
        import os
        import sys

        sys.path.append(os.path.dirname(os.path.abspath(__file__)))

        from testmcpy.src.llm_integration import create_llm_provider
        from testmcpy.src.mcp_client import MCPClient

        # Initialize LLM
        llm = create_llm_provider(provider.value, model)
        await llm.initialize()

        tools = []
        mcp_client = None

        if not no_mcp:
            try:
                # Initialize MCP client
                mcp_client = MCPClient(effective_mcp_url)
                await mcp_client.initialize()

                # Get available tools
                tools = await mcp_client.list_tools()
                console.print(
                    f"[green]Connected to MCP service with {len(tools)} tools available[/green]\n"
                )
            except Exception as e:
                console.print(f"[yellow]MCP connection failed: {e}[/yellow]")
                console.print("[yellow]Continuing without MCP tools...[/yellow]\n")

        if not tools:
            console.print("[dim]Interactive mode: Standalone (no tools available)[/dim]\n")

        # Interactive loop
        while True:
            try:
                # Get user input
                user_input = console.input("[bold blue]You:[/bold blue] ")

                if user_input.lower() in ["exit", "quit", "bye"]:
                    console.print("[yellow]Goodbye![/yellow]")
                    break

                if not user_input.strip():
                    continue

                # Show thinking indicator
                with console.status("[dim]Thinking...[/dim]"):
                    # Convert MCPTool objects to dictionaries for LLM
                    tools_dict = []
                    for tool in tools:
                        tools_dict.append(
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "inputSchema": tool.input_schema,
                            }
                        )

                    # Generate response with available tools
                    response = await llm.generate_with_tools(user_input, tools_dict)

                # Display response
                console.print(f"[bold green]{model}:[/bold green] {response.response}")

                # Show tool calls if any
                if response.tool_calls:
                    console.print(f"[dim]Used {len(response.tool_calls)} tool call(s)[/dim]")
                    for tool_call in response.tool_calls:
                        console.print(f"[dim]→ {tool_call['name']}({tool_call['arguments']})[/dim]")

                console.print()  # Empty line for spacing

            except KeyboardInterrupt:
                console.print("\n[yellow]Session interrupted. Goodbye![/yellow]")
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        # Cleanup
        if mcp_client:
            await mcp_client.close()
        await llm.close()

    asyncio.run(interact_session())
