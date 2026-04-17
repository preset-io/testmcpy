"""Interactive wizard commands for adding MCP servers, LLM providers, and tests."""

import asyncio
import re
from pathlib import Path

import typer
import yaml
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.syntax import Syntax
from rich.table import Table

from testmcpy.cli.app import app, console


def _prompt(label: str, default: str = "", password: bool = False) -> str:
    """Prompt user for input with optional default."""
    if default:
        return Prompt.ask(f"[bold]{label}[/bold]", default=default, password=password)
    return Prompt.ask(f"[bold]{label}[/bold]", password=password)


def _choose(label: str, choices: list[str], default: str | None = None) -> str:
    """Prompt user to choose from a list."""
    console.print(f"\n[bold]{label}[/bold]")
    for i, choice in enumerate(choices, 1):
        marker = "[green]*[/green] " if choice == default else "  "
        console.print(f"  {marker}{i}. {choice}")

    while True:
        raw = Prompt.ask("Enter number", default="1")
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        console.print("[red]Invalid choice, try again.[/red]")


@app.command(name="add-mcp")
def add_mcp():
    """
    Interactive wizard to add an MCP server to your configuration.

    Walks you through: name, transport, connection, auth, test, and save.
    """
    console.print(
        Panel(
            "[bold cyan]Add MCP Server[/bold cyan]\n"
            "[dim]Follow the prompts to configure a new MCP server.[/dim]",
            border_style="cyan",
        )
    )

    # Step 1: Name
    console.print("\n[bold yellow]Step 1: Server Info[/bold yellow]")
    name = _prompt("Server name", "my-mcp-server")

    # Step 2: Transport
    console.print("\n[bold yellow]Step 2: Transport[/bold yellow]")
    transport = _choose("Transport type:", ["sse", "stdio"], default="sse")

    # Step 3: Connection
    console.print("\n[bold yellow]Step 3: Connection[/bold yellow]")
    mcp_url = ""
    command = ""
    args_str = ""

    if transport == "stdio":
        command = _prompt("Command (e.g., npx, python, node)")
        args_str = _prompt("Arguments (space-separated)", "")
    else:
        mcp_url = _prompt("MCP URL", "https://api.example.com/mcp/")

    timeout = IntPrompt.ask("[bold]Timeout (seconds)[/bold]", default=30)
    rate_limit = IntPrompt.ask("[bold]Rate limit (req/min)[/bold]", default=60)

    # Step 4: Auth
    console.print("\n[bold yellow]Step 4: Authentication[/bold yellow]")
    auth_type = _choose("Auth type:", ["none", "bearer", "jwt", "oauth"], default="none")

    auth_config: dict = {"type": auth_type}
    if auth_type == "bearer":
        token = _prompt("Bearer token (or ${ENV_VAR})", password=True)
        auth_config["token"] = token
    elif auth_type == "jwt":
        auth_config["api_url"] = _prompt("API URL")
        auth_config["api_token"] = _prompt("API Token", password=True)
        auth_config["api_secret"] = _prompt("API Secret", password=True)
    elif auth_type == "oauth":
        auto_discover = Confirm.ask("Use OAuth auto-discovery (RFC 8414)?", default=False)
        if auto_discover:
            auth_config["oauth_auto_discover"] = True
        else:
            auth_config["client_id"] = _prompt("Client ID")
            auth_config["client_secret"] = _prompt("Client Secret", password=True)
            auth_config["token_url"] = _prompt("Token URL")
            scopes = _prompt("Scopes (comma-separated)", "")
            if scopes:
                auth_config["scopes"] = [s.strip() for s in scopes.split(",") if s.strip()]

    # Step 5: Test Connection
    console.print("\n[bold yellow]Step 5: Test Connection[/bold yellow]")
    if Confirm.ask("Test connection now?", default=True):
        from testmcpy.mcp_profiles import AuthConfig, MCPServer

        test_url = mcp_url if transport == "sse" else f"stdio://{command}"
        mcp_server = MCPServer(
            name=name,
            mcp_url=test_url,
            auth=AuthConfig(auth_type=auth_config.get("type", "none")),
            timeout=timeout,
            rate_limit_rpm=rate_limit,
            transport=transport,
            command=command if transport == "stdio" else None,
            args=args_str.split() if args_str else None,
        )

        console.print("[dim]Connecting...[/dim]")
        try:
            from testmcpy.src.mcp_client import MCPClient

            client = MCPClient(
                mcp_url=mcp_server.mcp_url,
                auth=mcp_server.auth.to_dict() if mcp_server.auth else None,
                timeout=mcp_server.timeout,
                transport=mcp_server.transport,
                command=mcp_server.command,
                args=mcp_server.args,
            )
            tools = asyncio.run(client.list_tools())
            console.print(f"[green]Connected! Found {len(tools)} tools.[/green]")
            if tools:
                tool_names = [t.name if hasattr(t, "name") else str(t) for t in tools[:5]]
                console.print(
                    f"[dim]  Tools: {', '.join(tool_names)}{'...' if len(tools) > 5 else ''}[/dim]"
                )
        except (ConnectionError, TimeoutError, OSError, RuntimeError, ValueError) as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            if not Confirm.ask("Continue anyway?", default=True):
                raise typer.Abort()

    # Step 6: Save
    console.print("\n[bold yellow]Step 6: Save[/bold yellow]")

    # Build MCP entry
    mcp_entry: dict = {"name": name, "timeout": timeout, "rate_limit_rpm": rate_limit}

    if transport == "stdio":
        mcp_entry["transport"] = "stdio"
        mcp_entry["command"] = command
        if args_str:
            mcp_entry["args"] = args_str.split()
        mcp_entry["mcp_url"] = f"stdio://{command}"
    else:
        mcp_entry["mcp_url"] = mcp_url

    if auth_type != "none":
        mcp_entry["auth"] = auth_config

    # Show preview
    console.print("\n[bold]Configuration preview:[/bold]")
    yaml_str = yaml.dump(mcp_entry, default_flow_style=False, sort_keys=False)
    console.print(Syntax(yaml_str, "yaml", theme="monokai"))

    # Load existing config
    config_path = Path.cwd() / ".mcp_services.yaml"
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {"default": "local-dev", "profiles": {}}

    profiles = config.get("profiles", {})
    profile_ids = list(profiles.keys())

    if profile_ids:
        target_profile = _choose("Add to profile:", profile_ids, default=profile_ids[0])
    else:
        target_profile = _prompt("Profile ID to create", "local-dev")
        profiles[target_profile] = {
            "name": target_profile,
            "description": "Created by wizard",
            "mcps": [],
        }
        config["profiles"] = profiles
        if "default" not in config:
            config["default"] = target_profile

    # Add MCP to profile
    profile = profiles[target_profile]
    if "mcps" not in profile:
        profile["mcps"] = []
    profile["mcps"].append(mcp_entry)

    # Write config
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    console.print(f"\n[green]MCP server '{name}' added to profile '{target_profile}'![/green]")
    console.print(f"[dim]Config saved to {config_path}[/dim]")


@app.command(name="add-llm")
def add_llm():
    """
    Interactive wizard to add an LLM provider to your configuration.

    Walks you through: provider type, model, API key, test, and save.
    """
    console.print(
        Panel(
            "[bold cyan]Add LLM Provider[/bold cyan]\n"
            "[dim]Follow the prompts to configure a new LLM provider.[/dim]",
            border_style="cyan",
        )
    )

    # Step 1: Provider
    console.print("\n[bold yellow]Step 1: Provider Type[/bold yellow]")
    provider = _choose(
        "Provider:",
        ["anthropic", "openai", "google", "ollama", "claude-sdk", "claude-code"],
        default="anthropic",
    )

    # Step 2: Model
    console.print("\n[bold yellow]Step 2: Model Selection[/bold yellow]")

    from testmcpy.src.model_registry import get_models_by_provider

    models = get_models_by_provider(provider)
    if models:
        table = Table(title=f"Available {provider} models")
        table.add_column("#", style="dim")
        table.add_column("Model ID", style="cyan")
        table.add_column("Name")
        table.add_column("$/1M in", justify="right")
        table.add_column("$/1M out", justify="right")
        for i, m in enumerate(models, 1):
            default_marker = " *" if m.is_default else ""
            table.add_row(
                str(i),
                m.id,
                f"{m.name}{default_marker}",
                f"${m.input_price_per_1m:.2f}",
                f"${m.output_price_per_1m:.2f}",
            )
        console.print(table)

        raw = Prompt.ask("[bold]Model (number or ID)[/bold]", default="1")
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(models):
                model_id = models[idx].id
                model_name = models[idx].name
            else:
                model_id = raw
                model_name = raw
        except ValueError:
            model_id = raw
            model_name = raw
    else:
        model_id = _prompt("Model ID")
        model_name = _prompt("Display name", model_id)

    display_name = _prompt("Display name", model_name)

    # Step 3: API Key
    console.print("\n[bold yellow]Step 3: Credentials[/bold yellow]")

    api_key = ""
    api_key_env = ""
    base_url = ""

    if provider in ("claude-sdk", "claude-code"):
        console.print("[green]No API key needed - uses Claude Code authentication.[/green]")
    else:
        console.print("Enter API key directly or specify an environment variable name.")
        api_key = _prompt("API key (leave empty to use env var)", password=True)
        if not api_key:
            default_env = {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai": "OPENAI_API_KEY",
                "google": "GOOGLE_API_KEY",
            }.get(provider, "")
            api_key_env = _prompt("Environment variable name", default_env)

    if provider == "ollama":
        base_url = _prompt("Base URL", "http://localhost:11434")

    timeout = IntPrompt.ask("[bold]Timeout (seconds)[/bold]", default=60)
    is_default = Confirm.ask("Set as default provider?", default=True)

    # Step 4: Test
    console.print("\n[bold yellow]Step 4: Test[/bold yellow]")
    if Confirm.ask("Test credentials now?", default=True):
        console.print("[dim]Sending test prompt...[/dim]")
        try:
            import httpx

            test_data = {
                "provider": provider,
                "model": model_id,
                "timeout": timeout,
            }
            if api_key:
                test_data["api_key"] = api_key
            if api_key_env:
                test_data["api_key_env"] = api_key_env
            if base_url:
                test_data["base_url"] = base_url

            # Try via the running server first
            resp = httpx.post("http://localhost:8765/api/llm/test", json=test_data, timeout=timeout)
            result = resp.json()
            if result.get("success"):
                console.print(f"[green]Test passed! ({result.get('duration', 0):.2f}s)[/green]")
            else:
                console.print(f"[red]Test failed: {result.get('error', 'Unknown error')}[/red]")
        except (ConnectionError, TimeoutError, OSError, RuntimeError, ValueError) as e:
            console.print(f"[yellow]Could not test (server may not be running): {e}[/yellow]")

    # Step 5: Save
    console.print("\n[bold yellow]Step 5: Save[/bold yellow]")

    provider_entry: dict = {
        "name": display_name,
        "provider": provider,
        "model": model_id,
        "timeout": timeout,
        "default": is_default,
    }
    if api_key:
        provider_entry["api_key"] = api_key
    if api_key_env:
        provider_entry["api_key_env"] = api_key_env
    if base_url:
        provider_entry["base_url"] = base_url

    # Show preview
    console.print("\n[bold]Configuration preview:[/bold]")
    yaml_str = yaml.dump(provider_entry, default_flow_style=False, sort_keys=False)
    console.print(Syntax(yaml_str, "yaml", theme="monokai"))

    # Load existing config
    config_path = Path.cwd() / ".llm_providers.yaml"
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {"default": None, "profiles": {}}

    profiles = config.get("profiles", {})
    profile_ids = list(profiles.keys())

    if profile_ids:
        target_profile = _choose("Add to profile:", profile_ids, default=profile_ids[0])
    else:
        target_profile = _prompt("Profile ID to create", "prod")
        profiles[target_profile] = {
            "name": "Production",
            "description": "Created by wizard",
            "providers": [],
        }
        config["profiles"] = profiles
        if not config.get("default"):
            config["default"] = target_profile

    # If setting as default, unset other defaults
    if is_default:
        for p in profiles.get(target_profile, {}).get("providers", []):
            p["default"] = False

    # Add provider
    profile = profiles[target_profile]
    if "providers" not in profile:
        profile["providers"] = []
    profile["providers"].append(provider_entry)

    # Write config
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    console.print(
        f"\n[green]LLM provider '{display_name}' added to profile '{target_profile}'![/green]"
    )
    console.print(f"[dim]Config saved to {config_path}[/dim]")


@app.command(name="add-test")
def add_test():
    """
    Interactive wizard to create a test case YAML file.

    Walks you through: file name, prompts, evaluators, and YAML preview.
    """
    console.print(
        Panel(
            "[bold cyan]Create Test Case[/bold cyan]\n"
            "[dim]Follow the prompts to create a new test YAML file.[/dim]",
            border_style="cyan",
        )
    )

    # Step 1: File name
    console.print("\n[bold yellow]Step 1: Test File[/bold yellow]")
    filename = _prompt("Test file name", "my_tests.yaml")
    if not filename.endswith(".yaml"):
        filename += ".yaml"
    # Sanitize filename: allow only alphanumeric, underscores, hyphens, dots
    if not re.match(r"^[a-zA-Z0-9._-]+$", filename):
        console.print(
            "[red]Invalid filename - only alphanumeric, underscores, hyphens, and dots allowed[/red]"
        )
        raise typer.Abort()

    # Step 2: Write tests
    console.print("\n[bold yellow]Step 2: Define Tests[/bold yellow]")

    evaluator_names = [
        "execution_successful",
        "was_mcp_tool_called",
        "final_answer_contains",
        "tool_called_with_params",
        "tool_call_count",
        "within_time_limit",
        "answer_contains_link",
        "sql_query_valid",
        "token_usage_reasonable",
    ]

    tests = []
    while True:
        console.print(f"\n[bold]Test #{len(tests) + 1}[/bold]")
        test_name = _prompt("Test name (empty to stop)")
        if not test_name:
            if not tests:
                console.print("[red]At least one test is required.[/red]")
                continue
            break

        prompt_text = _prompt("Prompt for the LLM")

        # Evaluators
        evaluators: list[dict] = []
        console.print("[dim]Add evaluators (empty name to stop):[/dim]")
        while True:
            ev_name = _choose(
                "Evaluator:",
                evaluator_names + ["(done)"],
                default="execution_successful",
            )
            if ev_name == "(done)":
                break

            ev_entry: dict = {"name": ev_name}

            # Prompt for args based on evaluator type
            if ev_name == "was_mcp_tool_called":
                tool = _prompt("Tool name")
                ev_entry["args"] = {"tool_name": tool}
            elif ev_name == "final_answer_contains":
                text = _prompt("Expected text")
                ev_entry["args"] = {"text": text}
            elif ev_name == "tool_called_with_params":
                tool = _prompt("Tool name")
                params_str = _prompt('Parameters (JSON, e.g., {"key": "value"})')
                ev_entry["args"] = {"tool_name": tool, "params": params_str}
            elif ev_name == "tool_call_count":
                tool = _prompt("Tool name")
                count = IntPrompt.ask("Expected count", default=1)
                ev_entry["args"] = {"tool_name": tool, "count": count}
            elif ev_name == "within_time_limit":
                seconds = IntPrompt.ask("Time limit (seconds)", default=30)
                ev_entry["args"] = {"seconds": seconds}
            elif ev_name == "token_usage_reasonable":
                max_tokens = IntPrompt.ask("Max tokens", default=10000)
                ev_entry["args"] = {"max_tokens": max_tokens}

            evaluators.append(ev_entry)

        if not evaluators:
            evaluators = [{"name": "execution_successful"}]

        tests.append({"name": test_name, "prompt": prompt_text, "evaluators": evaluators})

        if not Confirm.ask("Add another test?", default=False):
            break

    # Step 3: Preview & Save
    console.print("\n[bold yellow]Step 3: Preview & Save[/bold yellow]")

    yaml_data: dict = {"version": "1.0", "tests": tests}
    yaml_str = yaml.dump(yaml_data, default_flow_style=False, sort_keys=False)

    console.print("\n[bold]Generated YAML:[/bold]")
    console.print(Syntax(yaml_str, "yaml", theme="monokai"))

    # Determine test file path
    tests_dir = Path.cwd() / "tests"
    if not tests_dir.exists():
        tests_dir.mkdir(parents=True, exist_ok=True)

    file_path = (tests_dir / filename).resolve()
    if not file_path.is_relative_to(tests_dir.resolve()):
        console.print("[red]Invalid filename - must be within tests directory[/red]")
        raise typer.Abort()

    if file_path.exists():
        if not Confirm.ask(
            f"[yellow]{file_path} already exists. Overwrite?[/yellow]", default=False
        ):
            console.print("[dim]Aborted.[/dim]")
            raise typer.Abort()

    with open(file_path, "w") as f:
        f.write(yaml_str)

    console.print(f"\n[green]Test file created: {file_path}[/green]")
    console.print(f"[dim]Run with: testmcpy run --test {file_path}[/dim]")
