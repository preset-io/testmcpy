#!/usr/bin/env python3
"""
Validation script to check if the MCP Testing Framework is properly installed.
"""

import asyncio
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


async def validate_installation():
    """Validate the MCP Testing Framework installation."""
    console.print(
        Panel.fit(
            "[bold cyan]MCP Testing Framework - Installation Validation[/bold cyan]",
            border_style="cyan",
        )
    )

    results = []

    # Check imports
    console.print("\n[bold]Checking Python imports...[/bold]")

    try:
        import typer

        results.append(("typer", "✓", "Installed"))
    except ImportError:
        results.append(("typer", "✗", "Not installed"))

    try:
        import rich

        results.append(("rich", "✓", "Installed"))
    except ImportError:
        results.append(("rich", "✗", "Not installed"))

    try:
        import httpx

        results.append(("httpx", "✓", "Installed"))
    except ImportError:
        results.append(("httpx", "✗", "Not installed"))

    try:
        import yaml

        results.append(("pyyaml", "✓", "Installed"))
    except ImportError:
        results.append(("pyyaml", "✗", "Not installed"))

    try:
        import ollama

        results.append(("ollama", "✓", "Installed"))
    except ImportError:
        results.append(("ollama", "✗", "Not installed - optional"))

    # Check framework modules
    console.print("\n[bold]Checking framework modules...[/bold]")

    try:
        from src.mcp_client import MCPClient

        results.append(("MCP Client", "✓", "Available"))
    except ImportError as e:
        results.append(("MCP Client", "✗", f"Import error: {e}"))

    try:
        from src.llm_integration import create_llm_provider

        results.append(("LLM Integration", "✓", "Available"))
    except ImportError as e:
        results.append(("LLM Integration", "✗", f"Import error: {e}"))

    try:
        from src.test_runner import TestRunner

        results.append(("Test Runner", "✓", "Available"))
    except ImportError as e:
        results.append(("Test Runner", "✗", f"Import error: {e}"))

    try:
        from evals.base_evaluators import create_evaluator

        results.append(("Evaluators", "✓", "Available"))
    except ImportError as e:
        results.append(("Evaluators", "✗", f"Import error: {e}"))

    # Check Ollama connection
    console.print("\n[bold]Checking Ollama service...[/bold]")
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:11434/api/tags", timeout=2.0)
            if response.status_code == 200:
                models = response.json().get("models", [])
                if models:
                    model_names = [m["name"] for m in models]
                    results.append(("Ollama Service", "✓", f"{len(models)} models available"))
                    # Check for recommended models
                    recommended = ["llama3.1:8b", "mistral-nemo:latest", "qwen2.5:7b"]
                    for model in recommended:
                        if any(model in m for m in model_names):
                            results.append((f"  {model}", "✓", "Available"))
                else:
                    results.append(("Ollama Service", "⚠", "Running but no models"))
            else:
                results.append(("Ollama Service", "✗", "Not responding correctly"))
    except Exception:
        results.append(("Ollama Service", "✗", "Not running or not accessible"))

    # Check MCP service
    console.print("\n[bold]Checking MCP service...[/bold]")
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            # Try a simple request to the MCP endpoint
            response = await client.post(
                "http://localhost:5008/mcp/",
                json={"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1},
                timeout=2.0,
            )
            if response.status_code in [200, 404]:
                results.append(("MCP Service", "✓", "Responding"))
            else:
                results.append(("MCP Service", "⚠", f"HTTP {response.status_code}"))
    except Exception:
        results.append(("MCP Service", "✗", "Not accessible at localhost:5008"))

    # Display results
    console.print("\n[bold]Validation Results:[/bold]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Component", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Details")

    all_pass = True
    for component, status, details in results:
        if status == "✗":
            all_pass = False
            status_display = f"[red]{status}[/red]"
            details_display = f"[red]{details}[/red]"
        elif status == "⚠":
            status_display = f"[yellow]{status}[/yellow]"
            details_display = f"[yellow]{details}[/yellow]"
        else:
            status_display = f"[green]{status}[/green]"
            details_display = details

        table.add_row(component, status_display, details_display)

    console.print(table)

    # Final status
    console.print("")
    if all_pass:
        console.print(
            "[bold green]✓ All checks passed! The framework is ready to use.[/bold green]"
        )
        console.print("\nTry running:")
        console.print("  python cli.py research")
        console.print("  python cli.py tools")
        console.print("  python cli.py run tests/basic_test.yaml")
    else:
        console.print(
            "[bold yellow]⚠ Some checks failed. Please review the issues above.[/bold yellow]"
        )
        console.print("\nTo fix missing dependencies, run:")
        console.print("  pip install -r requirements.txt")
        console.print("\nFor Ollama models, run:")
        console.print("  ollama pull llama3.1:8b")

    return all_pass


if __name__ == "__main__":
    success = asyncio.run(validate_installation())
    sys.exit(0 if success else 1)
