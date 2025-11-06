"""
MCP Explorer screen for TUI.

Provides an interactive interface for browsing and exploring MCP tools,
resources, and prompts with detailed information and actions.
"""

import asyncio
import json
from pathlib import Path

from rich.syntax import Syntax
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, Static, TabbedContent, TabPane

from testmcpy.core.docs_optimizer import DocsOptimizer
from testmcpy.src.mcp_client import MCPClient, MCPTool
from testmcpy.tui.widgets.tool_tree import ToolTree


class ToolDetailPanel(Static):
    """Panel for displaying detailed tool information."""

    def __init__(self, *args, **kwargs):
        """Initialize the detail panel."""
        super().__init__(*args, **kwargs)
        self.current_tool: MCPTool | None = None

    def show_tool(self, tool: MCPTool):
        """
        Display details for a tool.

        Args:
            tool: MCPTool to display
        """
        self.current_tool = tool

        # Build detail content
        content = []

        # Tool name as header
        content.append(f"[bold cyan]{tool.name}[/bold cyan]\n")

        # Description
        content.append("[bold]Description:[/bold]")
        desc_lines = tool.description.split("\n")
        for line in desc_lines[:10]:  # Show first 10 lines
            content.append(f"  {line}")
        if len(desc_lines) > 10:
            content.append(f"  [dim]... and {len(desc_lines) - 10} more lines[/dim]")
        content.append("")

        # Input schema
        if tool.input_schema:
            content.append("[bold]Input Schema:[/bold]")

            props = tool.input_schema.get("properties", {})
            required = tool.input_schema.get("required", [])

            if props:
                content.append("")
                for param_name, param_info in props.items():
                    param_type = param_info.get("type", "any")
                    param_desc = param_info.get("description", "")
                    is_required = "[red]*[/red]" if param_name in required else " "

                    content.append(
                        f"  {is_required} [yellow]{param_name}[/yellow] ([cyan]{param_type}[/cyan])"
                    )
                    if param_desc:
                        # Wrap long descriptions
                        desc_words = param_desc.split()
                        lines = []
                        current_line = []
                        current_length = 0
                        for word in desc_words:
                            if current_length + len(word) + 1 > 60:
                                lines.append(" ".join(current_line))
                                current_line = [word]
                                current_length = len(word)
                            else:
                                current_line.append(word)
                                current_length += len(word) + 1
                        if current_line:
                            lines.append(" ".join(current_line))

                        for line in lines:
                            content.append(f"      [dim]{line}[/dim]")
                    content.append("")

                # Show JSON schema as well
                content.append("[bold]JSON Schema:[/bold]")
                schema_json = json.dumps(tool.input_schema, indent=2)
                content.append(f"[dim]{schema_json}[/dim]")
            else:
                content.append("  [dim]No parameters required[/dim]")
        else:
            content.append("[dim]No input schema defined[/dim]")

        # Update the panel
        self.update("\n".join(content))

    def clear_content(self):
        """Clear the detail panel."""
        self.current_tool = None
        self.update("[dim]Select a tool to view details[/dim]")


class ExplorerScreen(Screen):
    """Screen for exploring MCP tools, resources, and prompts."""

    BINDINGS = [
        ("h", "home", "Home"),
        ("escape", "home", "Home"),
        ("/", "search", "Search"),
        ("t", "generate_test", "Generate Test"),
        ("o", "optimize_docs", "Optimize Docs"),
        ("g", "ai_test", "AI Test"),
        ("r", "refresh", "Refresh"),
        ("q", "quit", "Quit"),
    ]

    CSS = """
    ExplorerScreen {
        layout: vertical;
    }

    #explorer_container {
        layout: horizontal;
        height: 100%;
    }

    #left_panel {
        width: 35%;
        border-right: solid cyan;
    }

    #right_panel {
        width: 65%;
        padding: 1 2;
    }

    #search_container {
        height: 3;
        padding: 0 1;
    }

    #tree_container {
        height: 1fr;
    }

    #status_bar {
        height: 1;
        background: $panel;
        color: $text;
        padding: 0 1;
    }

    ToolTree {
        height: 100%;
    }

    ToolDetailPanel {
        height: 100%;
        overflow-y: auto;
    }

    Input {
        width: 100%;
    }
    """

    def __init__(
        self,
        mcp_url: str,
        profile_name: str,
        auth: dict | None = None,
        *args,
        **kwargs,
    ):
        """
        Initialize the explorer screen.

        Args:
            mcp_url: URL of the MCP service
            profile_name: Name of the MCP profile
            auth: Authentication configuration
        """
        super().__init__(*args, **kwargs)
        self.mcp_url = mcp_url
        self.profile_name = profile_name
        self.auth = auth
        self.current_tab = "tools"
        self._tools_cache: list[MCPTool] = []

    def compose(self) -> ComposeResult:
        """Compose the explorer screen."""
        yield Header()

        # Main container with split layout
        with Horizontal(id="explorer_container"):
            # Left panel: Tool tree with search
            with Vertical(id="left_panel"):
                with Container(id="search_container"):
                    yield Input(placeholder="Search tools...", id="search_input")

                with Container(id="tree_container"):
                    yield ToolTree(id="tool_tree")

            # Right panel: Tool details
            with VerticalScroll(id="right_panel"):
                yield ToolDetailPanel(id="tool_detail")

        # Status bar
        yield Static(
            f"[cyan]Profile:[/cyan] {self.profile_name} | [cyan]URL:[/cyan] {self.mcp_url}",
            id="status_bar",
        )
        yield Footer()

    def on_mount(self):
        """Handle mount event."""
        self.title = f"MCP Explorer - {self.profile_name}"
        self.sub_title = "Browse and explore MCP tools"

        # Load tools asynchronously
        self.load_tools()

    @work(exclusive=True)
    async def load_tools(self, force_refresh: bool = False):
        """
        Load tools from MCP service.

        Args:
            force_refresh: If True, bypass cache
        """
        tree = self.query_one("#tool_tree", ToolTree)
        status = self.query_one("#status_bar", Static)

        # Show loading status
        status.update("[yellow]Loading tools...[/yellow]")

        try:
            # Connect to MCP and get tools
            async with MCPClient(self.mcp_url, self.auth) as client:
                tools = await client.list_tools()
                self._tools_cache = tools

            # Categorize tools
            categorized = self._categorize_tools(tools)

            # Load into tree
            tree.load_tools(categorized)

            # Update status
            total_tools = len(tools)
            status.update(
                f"[green]Loaded {total_tools} tools[/green]"
            )

        except Exception as e:
            status.update(f"[red]Error loading tools:[/red] {str(e)}")

    def _categorize_tools(self, tools: list[MCPTool]) -> dict[str, list[MCPTool]]:
        """
        Categorize tools based on their names and descriptions.

        Args:
            tools: List of MCPTool objects

        Returns:
            Dictionary mapping category names to lists of tools
        """
        categories = {
            "Charts & Dashboards": [],
            "Datasets": [],
            "SQL & Queries": [],
            "Other": [],
        }

        for tool in tools:
            name_lower = tool.name.lower()
            desc_lower = tool.description.lower()

            # Categorize based on name and description patterns
            if any(kw in name_lower or kw in desc_lower for kw in ["chart", "dashboard", "viz"]):
                categories["Charts & Dashboards"].append(tool)
            elif any(kw in name_lower or kw in desc_lower for kw in ["dataset", "table", "data"]):
                categories["Datasets"].append(tool)
            elif any(kw in name_lower or kw in desc_lower for kw in ["sql", "query", "execute"]):
                categories["SQL & Queries"].append(tool)
            else:
                categories["Other"].append(tool)

        # Remove empty categories
        return {k: v for k, v in categories.items() if v}

    @on(Input.Changed, "#search_input")
    def on_search_changed(self, event: Input.Changed):
        """Handle search input changes."""
        tree = self.query_one("#tool_tree", ToolTree)
        tree.filter_tools(event.value)

    @on(ToolTree.NodeHighlighted)
    def on_tool_selected(self, event: ToolTree.NodeHighlighted):
        """Handle tool selection in tree."""
        tree = self.query_one("#tool_tree", ToolTree)
        detail_panel = self.query_one("#tool_detail", ToolDetailPanel)

        tool = tree.get_selected_tool()
        if tool:
            detail_panel.show_tool(tool)
        else:
            detail_panel.clear_content()

    def action_home(self):
        """Return to home screen."""
        self.app.pop_screen()

    def action_search(self):
        """Focus the search input."""
        search_input = self.query_one("#search_input", Input)
        search_input.focus()

    def action_refresh(self):
        """Refresh tools from MCP service."""
        self.load_tools(force_refresh=True)

    def action_generate_test(self):
        """Generate a test for the selected tool."""
        tree = self.query_one("#tool_tree", ToolTree)
        tool = tree.get_selected_tool()

        if not tool:
            self.notify("No tool selected", severity="warning")
            return

        # Generate test file
        self._generate_test_file(tool)

    def action_optimize_docs(self):
        """Optimize documentation for the selected tool."""
        tree = self.query_one("#tool_tree", ToolTree)
        tool = tree.get_selected_tool()

        if not tool:
            self.notify("No tool selected", severity="warning")
            return

        # Run optimization
        self.optimize_tool_docs(tool)

    def action_ai_test(self):
        """Generate AI-powered test for the selected tool."""
        tree = self.query_one("#tool_tree", ToolTree)
        tool = tree.get_selected_tool()

        if not tool:
            self.notify("No tool selected", severity="warning")
            return

        self.notify("AI test generation not yet implemented", severity="information")

    def _generate_test_file(self, tool: MCPTool):
        """
        Generate a test file for a tool.

        Args:
            tool: MCPTool to generate test for
        """
        # Create test template
        test_content = {
            "version": "1.0",
            "tests": [
                {
                    "name": f"test_{tool.name}",
                    "prompt": f"[TODO: Add test prompt for {tool.name}]",
                    "evaluators": [
                        {"name": "was_mcp_tool_called", "args": {"tool_name": tool.name}},
                        {"name": "execution_successful"},
                    ],
                }
            ],
        }

        # Save to tests directory
        tests_dir = Path("tests")
        tests_dir.mkdir(exist_ok=True)

        import time

        test_file = tests_dir / f"test_{int(time.time() * 1000)}.yaml"

        import yaml

        with open(test_file, "w") as f:
            yaml.dump(test_content, f, default_flow_style=False, sort_keys=False)

        self.notify(f"Test file created: {test_file}", severity="information")

    @work(exclusive=True)
    async def optimize_tool_docs(self, tool: MCPTool):
        """
        Optimize documentation for a tool using AI.

        Args:
            tool: MCPTool to optimize
        """
        status = self.query_one("#status_bar", Static)
        status.update(f"[yellow]Optimizing docs for {tool.name}...[/yellow]")

        try:
            optimizer = DocsOptimizer()
            result = await optimizer.optimize_tool_docs(tool)
            await optimizer.close()

            # Show results
            self.notify(
                f"Optimization complete. Cost: ${result.cost:.4f}, Tokens: {result.tokens_used}",
                severity="information",
            )

            # Update detail panel with optimized docs
            detail_panel = self.query_one("#tool_detail", ToolDetailPanel)

            content = []
            content.append(f"[bold cyan]{tool.name}[/bold cyan] - [green]Optimized[/green]\n")

            content.append("[bold]Original Description:[/bold]")
            content.append(f"[dim]{result.original_description}[/dim]\n")

            content.append("[bold green]Improved Description:[/bold green]")
            content.append(f"{result.optimized_description}\n")

            content.append("[bold]Suggestions:[/bold]")
            for i, suggestion in enumerate(result.suggestions, 1):
                content.append(f"  {i}. {suggestion}")
            content.append("")

            if result.parameter_improvements:
                content.append("[bold]Parameter Improvements:[/bold]")
                for param, desc in result.parameter_improvements.items():
                    content.append(f"  [yellow]{param}:[/yellow] {desc}")

            detail_panel.update("\n".join(content))

            status.update(
                f"[green]Optimization complete[/green] | Cost: ${result.cost:.4f} | "
                f"Tokens: {result.tokens_used}"
            )

        except Exception as e:
            status.update(f"[red]Error optimizing docs:[/red] {str(e)}")
            self.notify(f"Optimization failed: {str(e)}", severity="error")
