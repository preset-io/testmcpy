"""Interactive commands: chat.

NOTE: TUI (Textual-based) interfaces have been removed from testmcpy.
We do not want TUI interfaces - they are complex, hard to maintain, and
often don't work reliably across different terminals.

Use the web UI (testmcpy serve) for visual exploration, or the CLI commands
for programmatic access. The chat command uses a simple REPL interface.
"""

import asyncio
from typing import Optional

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
def chat(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="MCP profile to use"),
    provider: ModelProvider = typer.Option(
        DEFAULT_PROVIDER, "--provider", help="LLM provider (anthropic, openai, ollama)"
    ),
    model: str = typer.Option(DEFAULT_MODEL, "--model", "-m", help="Model name"),
    mcp_url: Optional[str] = typer.Option(None, "--mcp-url", help="MCP service URL"),
    no_mcp: bool = typer.Option(False, "--no-mcp", help="Chat without MCP tools"),
):
    """
    Interactive chat with LLM that has access to MCP tools.

    Start an interactive session where you can chat with an LLM and it can use
    MCP tools from your service. Tool calls are displayed in real-time.

    Type 'exit', 'quit', or press Ctrl+C to end the session.

    Examples:
        testmcpy chat                          # Use default config
        testmcpy chat --profile prod           # Use specific MCP profile
        testmcpy chat --model claude-sonnet-4-20250514  # Use specific model
        testmcpy chat --no-mcp                 # Chat without MCP tools
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

    if no_mcp:
        console.print(
            Panel.fit(
                f"[bold cyan]Chat with {model}[/bold cyan]\n"
                f"Provider: {provider.value}\nMode: Standalone (no MCP tools)\n\n"
                "[dim]Type your message and press Enter. "
                "Type 'exit' or 'quit' to end session.[/dim]",
                border_style="cyan",
            )
        )
    else:
        console.print(
            Panel.fit(
                f"[bold cyan]Chat with {model}[/bold cyan]\n"
                f"Provider: {provider.value}\n"
                f"MCP: {effective_mcp_url}\n"
                f"Profile: {effective_profile or 'none'}\n"
                f"Auth: {auth_config.get('type', 'none') if auth_config else 'none'}\n\n"
                "[dim]Type your message and press Enter. "
                "Type 'exit' or 'quit' to end session.[/dim]",
                border_style="cyan",
            )
        )

    async def chat_session():
        from testmcpy.src.llm_integration import create_llm_provider
        from testmcpy.src.mcp_client import MCPClient, MCPToolCall

        # Initialize LLM
        llm = create_llm_provider(provider.value, model)
        await llm.initialize()

        tools = []
        mcp_client = None

        if not no_mcp:
            try:
                # Initialize MCP client with auth
                mcp_client = MCPClient(effective_mcp_url, auth=auth_config)
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
            console.print("[dim]Chat mode: Standalone (no tools available)[/dim]\n")

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
                    tools_dict = [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": tool.input_schema,
                        }
                        for tool in tools
                    ]

                    # Generate response with available tools
                    response = await llm.generate_with_tools(user_input, tools_dict)

                # Execute tool calls if any and MCP client available
                if response.tool_calls and mcp_client:
                    console.print(
                        f"[dim]Executing {len(response.tool_calls)} tool call(s)...[/dim]"
                    )
                    for tool_call in response.tool_calls:
                        tool_name = tool_call.get("name", "unknown")
                        tool_args = tool_call.get("arguments", {})
                        console.print(f"[cyan]→ {tool_name}[/cyan]")

                        try:
                            mcp_call = MCPToolCall(
                                id=f"chat_{tool_name}",
                                name=tool_name,
                                arguments=tool_args,
                            )
                            result = await mcp_client.call_tool(mcp_call)
                            if result.is_error:
                                console.print(f"  [red]Error: {result.error_message}[/red]")
                            else:
                                # Show truncated result
                                content_str = str(result.content)[:500]
                                if len(str(result.content)) > 500:
                                    content_str += "..."
                                console.print(f"  [dim]{content_str}[/dim]")
                        except Exception as e:
                            console.print(f"  [red]Tool error: {e}[/red]")

                    console.print()

                # Display response
                console.print(f"[bold green]{model}:[/bold green] {response.response}")
                console.print()  # Empty line for spacing

            except KeyboardInterrupt:
                console.print("\n[yellow]Session interrupted. Goodbye![/yellow]")
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                import traceback

                console.print(f"[dim]{traceback.format_exc()}[/dim]")

        # Cleanup
        if mcp_client:
            await mcp_client.close()
        await llm.close()

    asyncio.run(chat_session())
