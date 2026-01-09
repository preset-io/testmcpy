"""Server and setup commands: init, setup, serve, config_cmd, config_mcp, doctor."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from testmcpy.cli.app import (
    DEFAULT_MCP_URL,
    DEFAULT_MODEL,
    DEFAULT_PROVIDER,
    app,
    console,
    print_logo,
)
from testmcpy.config import get_config


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Directory to initialize"),
):
    """
    Initialize a new MCP test project.

    This command creates the standard directory structure and example files.
    """
    console.print(
        Panel.fit(
            "[bold cyan]MCP Testing Framework - Initialize Project[/bold cyan]",
            border_style="cyan",
        )
    )

    # Create directories
    dirs = ["tests", "evals"]
    for dir_name in dirs:
        dir_path = path / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓ Created {dir_path}[/green]")

    # Create example test file
    example_test = {
        "version": "1.0",
        "tests": [
            {
                "name": "test_get_chart_data",
                "prompt": "Get the data for chart with ID 123",
                "evaluators": [
                    {"name": "was_mcp_tool_called", "args": {"tool_name": "get_chart"}},
                    {"name": "execution_successful"},
                    {"name": "final_answer_contains", "args": {"expected_content": "chart"}},
                ],
            },
            {
                "name": "test_create_dashboard",
                "prompt": "Create a new dashboard called 'Sales Overview' with a bar chart",
                "evaluators": [
                    {"name": "was_superset_chart_created"},
                    {"name": "execution_successful"},
                    {"name": "within_time_limit", "args": {"max_seconds": 30}},
                ],
            },
        ],
    }

    test_file = path / "tests" / "example_tests.yaml"
    test_file.write_text(yaml.dump(example_test, default_flow_style=False))
    console.print(f"[green]✓ Created example test file: {test_file}[/green]")

    # Create config file
    project_config = {
        "mcp_url": DEFAULT_MCP_URL,
        "default_model": DEFAULT_MODEL,
        "default_provider": DEFAULT_PROVIDER,
        "evaluators": {"timeout": 30, "max_tokens": 2000, "max_cost": 0.10},
    }

    config_file = path / "mcp_test_config.yaml"
    config_file.write_text(yaml.dump(project_config, default_flow_style=False))
    console.print(f"[green]✓ Created config file: {config_file}[/green]")

    console.print("\n[bold green]Project initialized successfully![/bold green]")
    console.print("\nNext steps:")
    console.print("1. Edit tests/example_tests.yaml to add your test cases")
    console.print("2. Run: testmcpy research  # To test your model")
    console.print("3. Run: testmcpy run tests/  # To run all tests")


@app.command()
def setup(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config files"),
):
    """
    Interactive setup wizard for testmcpy configuration.

    Guides you through configuring MCP service profiles and LLM providers.
    Creates .llm_providers.yaml and .mcp_services.yaml in current directory.
    """
    from testmcpy.config import get_config

    console.print(
        Panel.fit(
            "[bold cyan]testmcpy Interactive Setup[/bold cyan]\n"
            "[dim]Configure MCP service profiles and LLM providers[/dim]",
            border_style="cyan",
        )
    )

    # Load current config to show existing values and detect env vars
    current_config = get_config()

    # Check for existing files
    llm_yaml_path = Path.cwd() / ".llm_providers.yaml"
    mcp_yaml_path = Path.cwd() / ".mcp_services.yaml"

    if (llm_yaml_path.exists() or mcp_yaml_path.exists()) and not force:
        console.print("\n[yellow]Configuration files already exist:[/yellow]")
        if llm_yaml_path.exists():
            console.print(f"  • {llm_yaml_path}")
        if mcp_yaml_path.exists():
            console.print(f"  • {mcp_yaml_path}")
        overwrite = console.input("\nOverwrite? [y/N]: ").strip().lower()
        if overwrite not in ["y", "yes"]:
            console.print("[yellow]Setup cancelled[/yellow]")
            return

    # ============================================================
    # LLM Provider Configuration
    # ============================================================
    console.print("\n[bold cyan]━━━ LLM Provider Configuration ━━━[/bold cyan]\n")

    # Detect API keys from environment
    env_anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    env_openai_key = os.environ.get("OPENAI_API_KEY")

    # Show detected environment variables
    if env_anthropic_key or env_openai_key:
        console.print("[green]✓ Detected API keys in environment:[/green]")
        if env_anthropic_key:
            console.print(
                f"  • ANTHROPIC_API_KEY: {env_anthropic_key[:8]}...{env_anthropic_key[-4:]}"
            )
        if env_openai_key:
            console.print(f"  • OPENAI_API_KEY: {env_openai_key[:8]}...{env_openai_key[-4:]}")
        console.print()

    # Ask which provider to use
    console.print("[bold]Select LLM Provider:[/bold]")
    console.print("1. [cyan]Anthropic[/cyan] - Claude models (best tool calling)")
    console.print("2. [cyan]OpenAI[/cyan] - GPT models")
    console.print("3. [cyan]Ollama[/cyan] - Local models (free, requires ollama serve)")

    provider_choice = console.input("\nChoice [1]: ").strip() or "1"

    llm_config = {"default": "prod", "profiles": {}}

    if provider_choice == "1":
        # Anthropic
        console.print("\n[bold]Anthropic Configuration:[/bold]")
        console.print("1. [cyan]claude-sonnet-4-5[/cyan] - Latest Sonnet 4.5 (most capable)")
        console.print("2. [cyan]claude-haiku-4-5[/cyan] - Latest Haiku 4.5 (fast & efficient)")
        console.print("3. [cyan]claude-opus-4-1[/cyan] - Latest Opus 4.1 (most powerful)")

        model_choice = console.input("\nChoice [1]: ").strip() or "1"
        model = "claude-sonnet-4-5"
        if model_choice == "2":
            model = "claude-haiku-4-5"
        elif model_choice == "3":
            model = "claude-opus-4-1"

        # API Key
        if env_anthropic_key:
            console.print(
                f"\n[green]Using Anthropic API key from environment:[/green] "
                f"{env_anthropic_key[:8]}...{env_anthropic_key[-4:]}"
            )
            use_env = console.input("Save this key to .llm_providers.yaml? [Y/n]: ").strip().lower()
            if use_env in ["", "y", "yes"]:
                api_key = env_anthropic_key
            else:
                api_key = console.input("Enter different API key: ").strip()
        else:
            api_key = console.input("\nAnthropic API Key: ").strip()

        llm_config["profiles"]["prod"] = {
            "name": "Production",
            "description": "High-quality models for production use",
            "providers": [
                {
                    "name": f"Claude {model}",
                    "provider": "anthropic",
                    "model": model,
                    "api_key": api_key,
                    "timeout": 60,
                    "default": True,
                }
            ],
        }

    elif provider_choice == "2":
        # OpenAI
        console.print("\n[bold]OpenAI Configuration:[/bold]")
        console.print("1. [cyan]gpt-4o[/cyan] - GPT-4 Optimized (recommended)")
        console.print("2. [cyan]gpt-4-turbo[/cyan] - GPT-4 Turbo")
        console.print("3. [cyan]gpt-3.5-turbo[/cyan] - GPT-3.5 Turbo (faster, cheaper)")

        model_choice = console.input("\nChoice [1]: ").strip() or "1"
        model = "gpt-4o"
        if model_choice == "2":
            model = "gpt-4-turbo"
        elif model_choice == "3":
            model = "gpt-3.5-turbo"

        # API Key
        if env_openai_key:
            console.print(
                f"\n[green]Using OpenAI API key from environment:[/green] "
                f"{env_openai_key[:8]}...{env_openai_key[-4:]}"
            )
            use_env = console.input("Save this key to .llm_providers.yaml? [Y/n]: ").strip().lower()
            if use_env in ["", "y", "yes"]:
                api_key = env_openai_key
            else:
                api_key = console.input("Enter different API key: ").strip()
        else:
            api_key = console.input("\nOpenAI API Key: ").strip()

        llm_config["profiles"]["prod"] = {
            "name": "Production",
            "description": "High-quality models for production use",
            "providers": [
                {
                    "name": f"OpenAI {model}",
                    "provider": "openai",
                    "model": model,
                    "api_key": api_key,
                    "timeout": 60,
                    "default": True,
                }
            ],
        }

    else:
        # Ollama
        console.print("\n[bold]Ollama Configuration:[/bold]")
        console.print("1. [cyan]llama3.1:8b[/cyan] - Meta's Llama 3.1 8B (good balance)")
        console.print("2. [cyan]qwen2.5:14b[/cyan] - Alibaba's Qwen 2.5 14B (strong coding)")
        console.print("3. [cyan]mistral:7b[/cyan] - Mistral 7B (efficient)")

        model_choice = console.input("\nChoice [1]: ").strip() or "1"
        model = "llama3.1:8b"
        if model_choice == "2":
            model = "qwen2.5:14b"
        elif model_choice == "3":
            model = "mistral:7b"

        base_url = (
            console.input("\nOllama Base URL [http://localhost:11434]: ").strip()
            or "http://localhost:11434"
        )

        llm_config["profiles"]["prod"] = {
            "name": "Production",
            "description": "Local Ollama models",
            "providers": [
                {
                    "name": f"Ollama {model}",
                    "provider": "ollama",
                    "model": model,
                    "base_url": base_url,
                    "timeout": 120,
                    "default": True,
                }
            ],
        }

    # Save LLM config
    llm_yaml_path.write_text(yaml.dump(llm_config, default_flow_style=False, sort_keys=False))
    console.print(f"\n[green]✓ LLM configuration saved to:[/green] {llm_yaml_path}")

    # ============================================================
    # MCP Service Configuration
    # ============================================================
    console.print("\n[bold cyan]━━━ MCP Service Configuration ━━━[/bold cyan]\n")

    # Show current MCP URL if set
    current_mcp_url = current_config.get_mcp_url()
    if current_mcp_url and current_mcp_url != "http://localhost:5008/mcp/":
        source = current_config.get_source("MCP_URL")
        console.print(f"[green]✓ MCP Service URL detected[/green] ({source})")
        console.print(f"[dim]  Current: {current_mcp_url}[/dim]")
        mcp_url = (
            console.input("  New URL (or press Enter to keep current): ").strip() or current_mcp_url
        )
    else:
        mcp_url = console.input("MCP Service URL [https://your-instance.example.com/mcp]: ").strip()

    if not mcp_url:
        console.print("[yellow]Skipping MCP configuration[/yellow]")
        console.print(f"[dim]You can configure MCP later by editing {mcp_yaml_path}[/dim]")
    else:
        # Ask for authentication method
        console.print("\n[bold]MCP Authentication Method:[/bold]")

        # Detect current auth method
        has_dynamic_jwt = all(
            [
                current_config.get("MCP_AUTH_API_URL"),
                current_config.get("MCP_AUTH_API_TOKEN"),
                current_config.get("MCP_AUTH_API_SECRET"),
            ]
        )
        has_static_token = current_config.get("MCP_AUTH_TOKEN") or current_config.get(
            "SUPERSET_MCP_TOKEN"
        )

        if has_dynamic_jwt:
            console.print("[dim]Currently configured: Dynamic JWT[/dim]")
        elif has_static_token:
            console.print("[dim]Currently configured: Static Token[/dim]")

        console.print("1. [cyan]Dynamic JWT[/cyan] - Fetch token from auth API (recommended)")
        console.print("2. [cyan]Static Token[/cyan] - Use a pre-generated bearer token")
        console.print("3. [cyan]None[/cyan] - No authentication required")

        default_auth = "1" if has_dynamic_jwt or not has_static_token else "2"
        auth_method = console.input(f"\nChoice [{default_auth}]: ").strip() or default_auth

        auth_config = {}

        if auth_method == "1":
            # Dynamic JWT
            current_api_url = current_config.get("MCP_AUTH_API_URL")
            if current_api_url:
                console.print(f"[dim]Current Auth API URL: {current_api_url}[/dim]")
                api_url = (
                    console.input("  New URL (or press Enter to keep current): ").strip()
                    or current_api_url
                )
            else:
                api_url = console.input(
                    "Auth API URL (e.g., https://api.example.com/v1/auth/): "
                ).strip()

            current_api_token = current_config.get("MCP_AUTH_API_TOKEN")
            if current_api_token:
                masked = f"{current_api_token[:8]}...{current_api_token[-4:]}"
                console.print(f"[dim]Current API Token: {masked}[/dim]")
                api_token = (
                    console.input("  New token (or press Enter to keep current): ").strip()
                    or current_api_token
                )
            else:
                api_token = console.input("API Token: ").strip()

            current_api_secret = current_config.get("MCP_AUTH_API_SECRET")
            if current_api_secret:
                masked = f"{current_api_secret[:8]}...{current_api_secret[-4:]}"
                console.print(f"[dim]Current API Secret: {masked}[/dim]")
                api_secret = (
                    console.input("  New secret (or press Enter to keep current): ").strip()
                    or current_api_secret
                )
            else:
                api_secret = console.input("API Secret: ").strip()

            auth_config = {
                "auth_type": "jwt",
                "api_url": api_url,
                "api_token": api_token,
                "api_secret": api_secret,
            }

        elif auth_method == "2":
            # Static token
            current_token = current_config.get("MCP_AUTH_TOKEN") or current_config.get(
                "SUPERSET_MCP_TOKEN"
            )
            if current_token:
                masked = f"{current_token[:20]}...{current_token[-8:]}"
                console.print(f"[dim]Current Token: {masked}[/dim]")
                static_token = (
                    console.input("  New token (or press Enter to keep current): ").strip()
                    or current_token
                )
            else:
                static_token = console.input("Bearer Token: ").strip()

            auth_config = {
                "auth_type": "bearer",
                "token": static_token,
            }
        else:
            # No auth
            auth_config = {"auth_type": "none"}

        # Create MCP config
        mcp_config = {
            "default": "prod",
            "profiles": {
                "prod": {
                    "name": "Production",
                    "description": "Production MCP service",
                    "mcps": [
                        {
                            "name": "Superset MCP",
                            "mcp_url": mcp_url,
                            "auth": auth_config,
                            "timeout": 30,
                            "rate_limit_rpm": 60,
                            "default": True,
                        }
                    ],
                }
            },
        }

        # Save MCP config
        mcp_yaml_path.write_text(yaml.dump(mcp_config, default_flow_style=False, sort_keys=False))
        console.print(f"\n[green]✓ MCP configuration saved to:[/green] {mcp_yaml_path}")

    # Final summary
    console.print("\n[bold green]✓ Setup Complete![/bold green]")
    console.print("\n[bold]Configuration files created:[/bold]")
    console.print(f"  • {llm_yaml_path}")
    if mcp_yaml_path.exists():
        console.print(f"  • {mcp_yaml_path}")

    console.print("\n[bold]Next steps:[/bold]")
    console.print("1. Run: [cyan]testmcpy config-cmd[/cyan]  # Verify configuration")
    if mcp_yaml_path.exists():
        console.print("2. Run: [cyan]testmcpy tools[/cyan]  # List available MCP tools")
        console.print("3. Run: [cyan]testmcpy interact[/cyan]  # Start interactive session")
    console.print(
        "\n[dim]Note: You can edit these files manually or run setup again with --force[/dim]"
    )


@app.command()
def serve(
    port: int = typer.Option(8000, "--port", "-p", help="Port to run server on"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    dev: bool = typer.Option(False, "--dev", help="Run in development mode (don't build frontend)"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser automatically"),
):
    """
    Start web server for testmcpy UI.

    This command starts a FastAPI server that serves a beautiful React-based UI
    for inspecting MCP tools, interactive chat, and test management.
    """
    # Show logo
    print_logo()

    # Show authentication steps
    console.print("\n[bold cyan]Authentication Setup[/bold cyan]")
    console.print("[dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/dim]")

    # Load config
    console.print("  [1/4] Loading configuration...")
    from testmcpy.config import get_config

    cfg = get_config()
    console.print("  [green]✓[/green] Configuration loaded")

    # Check MCP URL
    console.print("\n  [2/4] Checking MCP service URL...")
    console.print(f"  [dim]    MCP URL: {cfg.get_mcp_url()}[/dim]")
    console.print(f"  [dim]    Source: {cfg.get_source('MCP_URL')}[/dim]")
    console.print("  [green]✓[/green] MCP URL configured")

    # Check authentication method
    console.print("\n  [3/4] Checking authentication method...")
    has_dynamic_jwt = all(
        [cfg.get("MCP_AUTH_API_URL"), cfg.get("MCP_AUTH_API_TOKEN"), cfg.get("MCP_AUTH_API_SECRET")]
    )
    has_static_token = cfg.get("MCP_AUTH_TOKEN") or cfg.get("SUPERSET_MCP_TOKEN")

    if has_dynamic_jwt:
        console.print("  [cyan]→[/cyan] Using dynamic JWT authentication")
        console.print(f"  [dim]    Auth API URL: {cfg.get('MCP_AUTH_API_URL')}[/dim]")
        console.print(
            f"  [dim]    API Token: {cfg.get('MCP_AUTH_API_TOKEN')[:8]}..."
            f"{cfg.get('MCP_AUTH_API_TOKEN')[-4:]}[/dim]"
        )
        console.print("  [green]✓[/green] Dynamic JWT configured")

        # Try to fetch token
        console.print("\n  [4/4] Fetching JWT token from API...")
        try:
            import requests

            response = requests.post(
                cfg.get("MCP_AUTH_API_URL"),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json={
                    "name": cfg.get("MCP_AUTH_API_TOKEN"),
                    "secret": cfg.get("MCP_AUTH_API_SECRET"),
                },
                timeout=10,
            )
            if response.status_code == 200:
                console.print("  [green]✓[/green] JWT token fetched successfully")
            else:
                console.print(
                    f"  [yellow]⚠[/yellow] Failed to fetch JWT token (status: {response.status_code})"
                )
                console.print("  [yellow]  Server will attempt to fetch token when needed[/yellow]")
        except Exception as e:
            console.print(f"  [yellow]⚠[/yellow] Failed to fetch JWT token: {str(e)}")
            console.print("  [yellow]  Server will attempt to fetch token when needed[/yellow]")
    elif has_static_token:
        static_token = cfg.get("MCP_AUTH_TOKEN") or cfg.get("SUPERSET_MCP_TOKEN")
        console.print("  [cyan]→[/cyan] Using static bearer token")
        console.print(f"  [dim]    Token: {static_token[:20]}...{static_token[-8:]}[/dim]")
        source = cfg.get_source("MCP_AUTH_TOKEN") or cfg.get_source("SUPERSET_MCP_TOKEN")
        console.print(f"  [dim]    Source: {source}[/dim]")
        console.print("  [green]✓[/green] Static token configured")
        console.print("\n  [4/4] Token validation skipped (static token)")
    else:
        console.print("  [yellow]⚠[/yellow] No authentication configured")
        console.print("  [yellow]  MCP service may require authentication[/yellow]")
        console.print("\n  [4/4] Authentication setup incomplete")

    console.print("[dim]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/dim]\n")

    console.print(
        Panel.fit(
            f"[bold cyan]testmcpy Web Server[/bold cyan]\nStarting server at http://{host}:{port}",
            border_style="cyan",
        )
    )

    import subprocess
    import time
    from pathlib import Path

    # Get paths
    Path(__file__).parent.parent.parent / "server"
    ui_dir = Path(__file__).parent.parent.parent / "ui"
    ui_dist = ui_dir / "dist"

    # Check if FastAPI is installed
    try:
        import fastapi  # noqa: F401
        import uvicorn
    except ImportError:
        console.print("[red]Error: FastAPI and uvicorn are required for the web server[/red]")
        console.print("Install with: pip install 'testmcpy[server]'", markup=False)
        return

    # Build frontend if not in dev mode and dist doesn't exist
    if not dev and not ui_dist.exists():
        console.print("\n[yellow]Frontend not built. Building now...[/yellow]")

        # Check if npm is available
        try:
            subprocess.run(["npm", "--version"], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            console.print("[red]Error: npm is required to build the frontend[/red]")
            console.print("Install Node.js from https://nodejs.org/")
            return

        # Install dependencies
        console.print("Installing npm dependencies...")
        result = subprocess.run(["npm", "install"], cwd=ui_dir, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]Failed to install dependencies:[/red]\n{result.stderr}")
            return

        # Build
        console.print("Building frontend...")
        result = subprocess.run(["npm", "run", "build"], cwd=ui_dir, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]Failed to build frontend:[/red]\n{result.stderr}")
            return

        console.print("[green]Frontend built successfully![/green]\n")

    elif dev:
        console.print(
            "[yellow]Running in dev mode - make sure to start the frontend separately:[/yellow]"
        )
        console.print(f"  cd {ui_dir} && npm run dev\n")

    # Open browser
    if not no_browser:
        import threading
        import webbrowser

        import requests

        def open_browser():
            # Wait for server to be ready by checking health endpoint
            url = f"http://{host}:{port}/"
            max_attempts = 30
            for _ in range(max_attempts):
                try:
                    response = requests.get(url, timeout=1)
                    if response.status_code == 200:
                        # Server is ready
                        webbrowser.open(url)
                        return
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                    pass
                time.sleep(0.2)  # Wait 200ms between attempts

            # If server didn't start after max attempts, open anyway
            webbrowser.open(url)

        threading.Thread(target=open_browser, daemon=True).start()

    # Start server
    console.print("[green]Server starting...[/green]")
    console.print(f"[dim]API docs available at http://{host}:{port}/docs[/dim]\n")

    try:
        import uvicorn

        from testmcpy.server.api import app as fastapi_app

        uvicorn.run(fastapi_app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")
    except Exception as e:
        console.print(f"[red]Server error:[/red] {e}")


@app.command()
def config_cmd(
    show_all: bool = typer.Option(
        False, "--all", "-a", help="Show all config values including unset ones"
    ),
):
    """
    Display current testmcpy configuration.

    Shows the configuration values and their sources (environment, config file, etc.).
    """
    console.print(Panel.fit("[bold cyan]testmcpy Configuration[/bold cyan]", border_style="cyan"))

    from testmcpy.config import get_config

    cfg = get_config()

    # Get all config values with sources
    all_config = cfg.get_all_with_sources()

    # Create table
    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="blue",
        title="[bold]Configuration Values[/bold]",
        title_style="bold magenta",
    )
    table.add_column("Key", style="bold green", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_column("Source", style="yellow")

    # Sort keys for better display
    sorted_keys = sorted(all_config.keys())

    for key in sorted_keys:
        value, source = all_config[key]

        # Mask sensitive values
        if "API_KEY" in key or "TOKEN" in key:
            if value:
                masked_value = f"{value[:8]}{'*' * (len(value) - 8)}" if len(value) > 8 else "***"
            else:
                masked_value = "[dim]not set[/dim]"
        else:
            masked_value = value or "[dim]not set[/dim]"

        table.add_row(key, masked_value, source)

    console.print(table)

    # Show config file locations
    console.print("\n[bold]Configuration Locations (priority order):[/bold]")
    console.print("1. [cyan]Command-line options[/cyan] (highest priority)")
    console.print(f"2. [cyan].env in current directory[/cyan] ({Path.cwd() / '.env'})")
    console.print(f"3. [cyan]~/.testmcpy[/cyan] ({Path.home() / '.testmcpy'})")
    console.print("4. [cyan]Environment variables[/cyan]")
    console.print("5. [cyan]Built-in defaults[/cyan] (lowest priority)")

    # Check which config files exist
    console.print("\n[bold]Config Files:[/bold]")
    cwd_env = Path.cwd() / ".env"
    user_config = Path.home() / ".testmcpy"

    if cwd_env.exists():
        console.print(f"[green]✓[/green] {cwd_env} (exists)")
    else:
        console.print(f"[dim]✗ {cwd_env} (not found)[/dim]")

    if user_config.exists():
        console.print(f"[green]✓[/green] {user_config} (exists)")
    else:
        console.print(f"[dim]✗ {user_config} (not found)[/dim]")
        console.print(f"\n[dim]Tip: Create {user_config} to set user defaults[/dim]")


@app.command()
def config_mcp(
    target: str = typer.Argument(
        ..., help="Target application: claude-desktop, claude-code, or chatgpt-desktop"
    ),
    server_name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Server name in config (default: superset)"
    ),
    mcp_url: Optional[str] = typer.Option(
        None, "--mcp-url", help="MCP service URL (uses config default if not provided)"
    ),
    auth_token: Optional[str] = typer.Option(
        None, "--token", help="Bearer token (uses dynamic JWT if not provided)"
    ),
):
    """
    Configure MCP server for Claude Desktop, Claude Code, or ChatGPT Desktop.

    This command automatically adds your MCP service configuration to the appropriate
    application config file. It supports:

    - claude-desktop: ~/Library/Application Support/Claude/claude_desktop_config.json
    - claude-code: ~/.claude.json or .mcp.json
    - chatgpt-desktop: Similar to claude-desktop format

    The command will use your current testmcpy configuration (MCP URL and auth)
    and format it appropriately for the target application.
    """
    import platform
    from pathlib import Path

    console.print(
        Panel.fit(f"[bold cyan]Configure MCP for {target}[/bold cyan]", border_style="cyan")
    )

    # Determine target config file path
    system = platform.system()
    target = target.lower()

    if target == "claude-desktop":
        if system == "Darwin":  # macOS
            config_path = (
                Path.home()
                / "Library"
                / "Application Support"
                / "Claude"
                / "claude_desktop_config.json"
            )
        elif system == "Windows":
            config_path = Path(os.getenv("APPDATA")) / "Claude" / "claude_desktop_config.json"
        else:  # Linux
            config_path = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"

    elif target == "claude-code":
        # Prefer ~/.claude.json for reliability
        config_path = Path.home() / ".claude.json"
        console.print(
            "[dim]Note: Using ~/.claude.json (recommended). "
            "You can also use .mcp.json in project directory.[/dim]\n"
        )

    elif target == "chatgpt-desktop":
        # ChatGPT Desktop uses similar format to Claude Desktop
        if system == "Darwin":  # macOS
            config_path = (
                Path.home() / "Library" / "Application Support" / "ChatGPT" / "config.json"
            )
        else:
            console.print(
                "[yellow]ChatGPT Desktop config location not well-documented for this OS.[/yellow]"
            )
            console.print(
                "[yellow]Please check ChatGPT Desktop documentation for config file location."
                "[/yellow]"
            )
            return

    else:
        console.print(f"[red]Error: Unknown target '{target}'[/red]")
        console.print("Supported targets: claude-desktop, claude-code, chatgpt-desktop")
        return

    # Get MCP configuration
    cfg = get_config()
    mcp_url = mcp_url or cfg.get_mcp_url()
    server_name = server_name or "superset"

    if not mcp_url:
        console.print("[red]Error: MCP URL not configured[/red]")
        console.print("Run: testmcpy setup")
        return

    # Get auth token
    if not auth_token:
        # Try to get auth from MCP profile first
        mcp_server = cfg.get_default_mcp_server()
        if mcp_server and mcp_server.auth:
            auth = mcp_server.auth

            if auth.auth_type == "bearer" and auth.token:
                # Static bearer token
                console.print("[green]✓ Using bearer token from MCP profile[/green]")
                auth_token = auth.token

            elif auth.auth_type == "jwt" and auth.api_url and auth.api_token and auth.api_secret:
                # Dynamic JWT - fetch token
                console.print(
                    "[yellow]Fetching bearer token using JWT from MCP profile...[/yellow]"
                )
                try:
                    import requests

                    console.print(f"[dim]Auth URL: {auth.api_url}[/dim]")
                    console.print(
                        f"[dim]API Token: {auth.api_token[:8]}...{auth.api_token[-4:]}[/dim]"
                    )

                    response = requests.post(
                        auth.api_url,
                        headers={"Content-Type": "application/json", "Accept": "application/json"},
                        json={"name": auth.api_token, "secret": auth.api_secret},
                        timeout=10,
                    )

                    console.print(f"[dim]Response status: {response.status_code}[/dim]")

                    if response.status_code != 200:
                        console.print(f"[red]Error: API returned {response.status_code}[/red]")
                        console.print(f"[red]Response: {response.text}[/red]")
                        console.print(
                            "[yellow]Please provide --token with a long-lived bearer token[/yellow]"
                        )
                        return

                    auth_data = response.json()
                    # Try both 'access_token' and 'payload.access_token' keys
                    auth_token = auth_data.get("access_token")
                    if not auth_token and "payload" in auth_data:
                        payload = auth_data["payload"]
                        if isinstance(payload, dict):
                            auth_token = payload.get("access_token")
                        else:
                            auth_token = payload

                    if auth_token:
                        console.print(
                            f"[green]✓ Successfully fetched bearer token "
                            f"(length: {len(auth_token)})[/green]"
                        )
                    else:
                        console.print("[red]Error: No access_token or payload in response[/red]")
                        console.print(f"[red]Response keys: {list(auth_data.keys())}[/red]")
                        console.print(f"[red]Full response: {auth_data}[/red]")
                        return
                except Exception as e:
                    console.print(f"[red]Error fetching token: {e}[/red]")
                    import traceback

                    console.print(f"[red]{traceback.format_exc()}[/red]")
                    console.print(
                        "[yellow]Please provide --token with a long-lived bearer token[/yellow]"
                    )
                    return
            elif auth.auth_type == "none":
                # No auth required
                console.print("[yellow]Note: MCP profile has auth_type: none[/yellow]")
                console.print(
                    "[yellow]Skipping authentication (you may need to add --token manually)"
                    "[/yellow]"
                )
                auth_token = ""  # Empty token for no-auth
            else:
                console.print(
                    f"[yellow]Warning: Unknown or incomplete auth type in MCP profile: "
                    f"{auth.auth_type}[/yellow]"
                )

        # Fallback to old env-var approach if no MCP profile auth
        if not auth_token:
            if (
                cfg.get("MCP_AUTH_API_URL")
                and cfg.get("MCP_AUTH_API_TOKEN")
                and cfg.get("MCP_AUTH_API_SECRET")
            ):
                console.print(
                    "[yellow]Fetching bearer token using legacy env vars "
                    "(MCP_AUTH_API_*)...[/yellow]"
                )
                try:
                    import requests

                    auth_url = cfg.get("MCP_AUTH_API_URL")
                    api_token = cfg.get("MCP_AUTH_API_TOKEN")
                    api_secret = cfg.get("MCP_AUTH_API_SECRET")

                    console.print(f"[dim]Auth URL: {auth_url}[/dim]")
                    console.print(f"[dim]API Token: {api_token[:8]}...{api_token[-4:]}[/dim]")

                    response = requests.post(
                        auth_url,
                        headers={"Content-Type": "application/json", "Accept": "application/json"},
                        json={"name": api_token, "secret": api_secret},
                        timeout=10,
                    )

                    console.print(f"[dim]Response status: {response.status_code}[/dim]")

                    if response.status_code != 200:
                        console.print(f"[red]Error: API returned {response.status_code}[/red]")
                        console.print(f"[red]Response: {response.text}[/red]")
                        console.print(
                            "[yellow]Please provide --token with a long-lived bearer token[/yellow]"
                        )
                        return

                    auth_data = response.json()
                    auth_token = auth_data.get("access_token")
                    if not auth_token and "payload" in auth_data:
                        payload = auth_data["payload"]
                        if isinstance(payload, dict):
                            auth_token = payload.get("access_token")
                        else:
                            auth_token = payload

                    if auth_token:
                        console.print(
                            f"[green]✓ Successfully fetched bearer token "
                            f"(length: {len(auth_token)})[/green]"
                        )
                    else:
                        console.print("[red]Error: No access_token or payload in response[/red]")
                        return
                except Exception as e:
                    console.print(f"[red]Error fetching token: {e}[/red]")
                    return
            else:
                console.print("[red]Error: No authentication token available[/red]")
                console.print("Options:")
                console.print("  1. Configure MCP profile in .mcp_services.yaml (recommended)")
                console.print("  2. Provide --token with a bearer token")
                console.print("  3. Configure legacy env vars (MCP_AUTH_API_*)")
                return

    # Create MCP server configuration
    mcp_args = ["-y", "mcp-remote@latest", mcp_url]

    # Only add Authorization header if we have a token (not empty for no-auth)
    if auth_token:
        mcp_args.extend(["--header", f"Authorization: Bearer {auth_token}"])

    mcp_server_config = {
        "command": "npx",
        "args": mcp_args,
        "env": {"NODE_OPTIONS": "--no-warnings"},
    }

    # Read existing config if it exists
    existing_config = {}
    if config_path.exists():
        try:
            with open(config_path) as f:
                existing_config = json.load(f)
            console.print(f"[green]✓ Found existing config at {config_path}[/green]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not read existing config: {e}[/yellow]")

    # Update config
    if "mcpServers" not in existing_config:
        existing_config["mcpServers"] = {}

    existing_config["mcpServers"][server_name] = mcp_server_config

    # Ensure parent directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Write config
    try:
        with open(config_path, "w") as f:
            json.dump(existing_config, f, indent=2)

        console.print("\n[green]✓ MCP server configured successfully![/green]")
        console.print(f"[green]✓ Config file: {config_path}[/green]")
        console.print(f"[green]✓ Server name: {server_name}[/green]")
        console.print(f"[green]✓ MCP URL: {mcp_url}[/green]")

        # Show the config that was added
        console.print("\n[bold]Added configuration:[/bold]")
        config_display = {
            server_name: {
                "command": "npx",
                "args": [
                    "-y",
                    "mcp-remote@latest",
                    mcp_url,
                    "--header",
                    f"Authorization: Bearer {auth_token[:20]}...{auth_token[-8:]}",
                ],
                "env": {"NODE_OPTIONS": "--no-warnings"},
            }
        }
        console.print(Syntax(json.dumps(config_display, indent=2), "json", theme="monokai"))

        # Next steps
        console.print("\n[bold]Next steps:[/bold]")
        if target == "claude-desktop":
            console.print("1. Restart Claude Desktop")
            console.print("2. The MCP server should appear in Claude's tool list")
        elif target == "claude-code":
            console.print("1. Restart Claude Code (or reload window)")
            console.print("2. The MCP server should be available")
            console.print("3. Use --mcp-debug flag if you encounter issues")
        elif target == "chatgpt-desktop":
            console.print("1. Restart ChatGPT Desktop")
            console.print("2. The MCP server should be available")

    except Exception as e:
        console.print(f"[red]Error writing config file:[/red] {e}")
        return


@app.command()
def doctor():
    """
    Run health checks to diagnose installation issues.

    This command checks Python version, dependencies, configuration,
    and MCP connectivity to help identify and resolve issues.
    """
    console.print(
        Panel.fit(
            "[bold cyan]testmcpy Health Check[/bold cyan]\n"
            "[dim]Diagnosing installation and configuration...[/dim]",
            border_style="cyan",
        )
    )

    issues_found = []
    warnings_found = []

    # 1. Check Python version
    console.print("\n[bold]1. Python Version[/bold]")

    python_version = sys.version_info
    version_str = f"{python_version.major}.{python_version.minor}.{python_version.micro}"

    if python_version >= (3, 9) and python_version < (3, 13):
        console.print(f"[green]✓[/green] Python {version_str} (compatible)")
    elif python_version < (3, 9):
        console.print(f"[red]✗[/red] Python {version_str} (too old, requires 3.9+)")
        issues_found.append(
            f"Python version {version_str} is too old. Requires Python 3.9 or higher."
        )
    else:
        console.print(f"[yellow]⚠[/yellow] Python {version_str} (not tested, may not work)")
        warnings_found.append(
            f"Python {version_str} is newer than 3.12 and has not been tested with testmcpy."
        )

    # 2. Check core dependencies
    console.print("\n[bold]2. Core Dependencies[/bold]")
    core_deps = [
        ("typer", "typer"),
        ("rich", "rich"),
        ("yaml", "pyyaml"),
        ("httpx", "httpx"),
        ("anthropic", "anthropic"),
        ("fastmcp", "fastmcp"),
        ("dotenv", "python-dotenv"),
    ]

    all_core_deps_ok = True
    for import_name, package_name in core_deps:
        try:
            __import__(import_name)
            console.print(f"[green]✓[/green] {package_name}")
        except ImportError:
            console.print(f"[red]✗[/red] {package_name} - not installed")
            issues_found.append(f"Missing required dependency: {package_name}")
            all_core_deps_ok = False

    # 3. Check optional dependencies
    console.print("\n[bold]3. Optional Dependencies[/bold]")

    # Server dependencies
    console.print("[dim]Server (Web UI):[/dim]")
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401

        console.print("[green]✓[/green] fastapi, uvicorn - Web UI available")
    except ImportError:
        console.print(
            "[dim]✗[/dim] fastapi, uvicorn - Install with: pip install 'testmcpy[server]'",
            markup=False,
        )

    # SDK dependency
    console.print("[dim]Claude Agent SDK:[/dim]")
    try:
        import claude_agent_sdk  # noqa: F401

        console.print("[green]✓[/green] claude-agent-sdk - SDK provider available")
    except ImportError:
        console.print(
            "[dim]✗[/dim] claude-agent-sdk - Install with: pip install 'testmcpy[sdk]'",
            markup=False,
        )

    # 4. Check configuration
    console.print("\n[bold]4. Configuration[/bold]")

    cfg = get_config()

    # Check MCP URL
    mcp_url = cfg.get_mcp_url()
    if mcp_url and mcp_url != "http://localhost:5008/mcp/":
        console.print(f"[green]✓[/green] MCP URL configured: {mcp_url}")
    else:
        console.print("[yellow]⚠[/yellow] MCP URL not configured (using default)")
        warnings_found.append("MCP URL not configured. Run: testmcpy setup")

    # Check authentication
    has_dynamic_jwt = all(
        [cfg.get("MCP_AUTH_API_URL"), cfg.get("MCP_AUTH_API_TOKEN"), cfg.get("MCP_AUTH_API_SECRET")]
    )
    has_static_token = cfg.get("MCP_AUTH_TOKEN") or cfg.get("SUPERSET_MCP_TOKEN")

    if has_dynamic_jwt:
        console.print("[green]✓[/green] MCP Authentication: Dynamic JWT configured")
    elif has_static_token:
        console.print("[green]✓[/green] MCP Authentication: Static token configured")
    else:
        console.print("[yellow]⚠[/yellow] MCP Authentication: Not configured")
        warnings_found.append("MCP authentication not configured. Run: testmcpy setup")

    # Check LLM provider
    provider = cfg.default_provider
    model = cfg.default_model
    if provider:
        console.print(f"[green]✓[/green] LLM Provider: {provider}")
        console.print(f"[dim]  Model: {model}[/dim]")

        # Check provider-specific API keys
        if provider == "anthropic":
            api_key = cfg.get("ANTHROPIC_API_KEY")
            if api_key:
                console.print("[green]✓[/green] Anthropic API key configured")
            else:
                console.print("[red]✗[/red] Anthropic API key missing")
                issues_found.append(
                    "Anthropic API key not configured. Set ANTHROPIC_API_KEY in ~/.testmcpy"
                )
        elif provider == "openai":
            api_key = cfg.get("OPENAI_API_KEY")
            if api_key:
                console.print("[green]✓[/green] OpenAI API key configured")
            else:
                console.print("[red]✗[/red] OpenAI API key missing")
                issues_found.append(
                    "OpenAI API key not configured. Set OPENAI_API_KEY in ~/.testmcpy"
                )
        elif provider == "ollama":
            base_url = cfg.get("OLLAMA_BASE_URL") or "http://localhost:11434"
            console.print(f"[dim]  Ollama URL: {base_url}[/dim]")
    else:
        console.print("[yellow]⚠[/yellow] LLM Provider: Not configured")
        warnings_found.append("LLM provider not configured. Run: testmcpy setup")

    # 5. Check MCP connectivity (if configured)
    if mcp_url and mcp_url != "http://localhost:5008/mcp/" and all_core_deps_ok:
        console.print("\n[bold]5. MCP Connectivity[/bold]")

        async def check_mcp():
            try:
                from testmcpy.src.mcp_client import MCPClient

                with console.status("[dim]Connecting to MCP service...[/dim]"):
                    client = MCPClient(mcp_url)
                    await client.initialize()
                    tools = await client.list_tools()
                    await client.close()

                console.print("[green]✓[/green] MCP service reachable")
                console.print(f"[dim]  Found {len(tools)} tools[/dim]")
                return True
            except Exception as e:
                console.print(f"[red]✗[/red] MCP service unreachable: {str(e)}")
                issues_found.append(f"Cannot connect to MCP service: {str(e)}")
                return False

        try:
            asyncio.run(check_mcp())
        except Exception as e:
            console.print(f"[red]✗[/red] MCP connectivity test failed: {str(e)}")
            issues_found.append(f"MCP connectivity test error: {str(e)}")
    else:
        console.print("\n[bold]5. MCP Connectivity[/bold]")
        console.print("[dim]Skipped (MCP not configured or missing dependencies)[/dim]")

    # 6. Check virtual environment
    console.print("\n[bold]6. Environment[/bold]")
    if hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    ):
        console.print("[green]✓[/green] Running in virtual environment")
        console.print(f"[dim]  Location: {sys.prefix}[/dim]")
    else:
        console.print("[yellow]⚠[/yellow] Not running in virtual environment")
        warnings_found.append(
            "Not using a virtual environment. Consider using: python3 -m venv venv"
        )

    # 7. Check config files
    console.print("\n[bold]7. Configuration Files[/bold]")
    cwd_env = Path.cwd() / ".env"
    user_config = Path.home() / ".testmcpy"

    config_files_exist = False
    if cwd_env.exists():
        console.print(f"[green]✓[/green] {cwd_env}")
        config_files_exist = True
    else:
        console.print(f"[dim]✗ {cwd_env} (not found)[/dim]")

    if user_config.exists():
        console.print(f"[green]✓[/green] {user_config}")
        config_files_exist = True
    else:
        console.print(f"[dim]✗ {user_config} (not found)[/dim]")

    if not config_files_exist:
        warnings_found.append("No configuration files found. Run: testmcpy setup")

    # Summary
    console.print("\n" + "=" * 50)
    if not issues_found and not warnings_found:
        console.print("\n[bold green]✓ All checks passed![/bold green]")
        console.print("[dim]Your testmcpy installation is healthy.[/dim]")
    else:
        if issues_found:
            console.print(f"\n[bold red]Found {len(issues_found)} issue(s):[/bold red]")
            for i, issue in enumerate(issues_found, 1):
                console.print(f"  {i}. {issue}")

        if warnings_found:
            console.print(f"\n[bold yellow]Found {len(warnings_found)} warning(s):[/bold yellow]")
            for i, warning in enumerate(warnings_found, 1):
                console.print(f"  {i}. {warning}")

        console.print("\n[bold]Recommended Actions:[/bold]")
        if any("Python version" in issue for issue in issues_found):
            console.print("• Upgrade Python to 3.9 or higher: https://www.python.org/downloads/")
        if any("Missing required dependency" in issue for issue in issues_found):
            console.print("• Reinstall testmcpy: pip install --upgrade testmcpy")
        if any("API key" in issue for issue in issues_found):
            console.print("• Configure API keys: testmcpy setup")
        if "MCP" in str(warnings_found) or "MCP" in str(issues_found):
            console.print("• Configure MCP service: testmcpy setup")
        if any("virtual environment" in warning for warning in warnings_found):
            console.print(
                "• Create virtual environment: python3 -m venv venv && source venv/bin/activate"
            )

    console.print()
