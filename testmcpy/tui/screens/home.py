"""
Home screen for testmcpy TUI dashboard.
"""

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, ScrollableContainer, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from testmcpy.mcp_profiles import get_profile_config
from testmcpy.tui.widgets.header import Header
from testmcpy.tui.widgets.mcp_status import MCPStatus


class HomeScreen(Screen):
    """Home dashboard screen showing MCP profiles and quick actions."""

    BINDINGS = [
        ("q", "app.quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    DEFAULT_CSS = """
    HomeScreen {
        background: $surface;
    }
    
    #main-container {
        height: 100%;
        width: 100%;
    }
    
    #profiles-section {
        height: auto;
        border: solid $primary;
        background: $panel;
        margin: 1;
        padding: 1;
    }
    
    #profiles-title {
        text-align: left;
        color: $accent;
        text-style: bold;
        padding-bottom: 1;
    }
    
    #profiles-list {
        height: auto;
    }
    
    #actions-section {
        height: auto;
        border: solid $primary;
        background: $panel;
        margin: 1;
        padding: 1;
    }
    
    #actions-title {
        text-align: left;
        color: $accent;
        text-style: bold;
        padding-bottom: 1;
    }
    
    .action-item {
        padding: 0 1;
        color: $text;
    }
    
    .action-item:hover {
        background: $primary;
    }
    
    #activity-section {
        height: auto;
        border: solid $primary;
        background: $panel;
        margin: 1;
        padding: 1;
    }
    
    #activity-title {
        text-align: left;
        color: $accent;
        text-style: bold;
        padding-bottom: 1;
    }
    
    .activity-item {
        padding: 0 1;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose home screen layout."""
        # Header
        yield Header(profile=None, connected=False)

        # Main scrollable container
        with VerticalScroll(id="main-container"):
            # MCP Profiles section
            with Container(id="profiles-section"):
                title_text = Text()
                title_text.append("MCP Profiles", style="bold cyan")
                title_text.append("                                        ", style="dim")
                title_text.append("[p] Profiles [c] Chat", style="dim")
                yield Static(title_text, id="profiles-title")

                # Load and display profiles
                yield from self._compose_profiles()

            # Quick Actions section
            with Container(id="actions-section"):
                title_text = Text()
                title_text.append("Quick Actions", style="bold cyan")
                title_text.append("                          ", style="dim")
                title_text.append("[t] Tests [e] Explorer [?] Help", style="dim")
                yield Static(title_text, id="actions-title")

                yield from self._compose_actions()

            # Recent Activity section
            with Container(id="activity-section"):
                yield Static("Recent Activity", id="activity-title")
                yield from self._compose_activity()

    def _compose_profiles(self) -> ComposeResult:
        """Compose MCP profiles list."""
        profile_config = get_profile_config()

        if not profile_config.has_profiles():
            # No profiles configured
            no_profiles_text = Text()
            no_profiles_text.append("  No MCP profiles configured\n", style="yellow")
            no_profiles_text.append(
                "  Run: testmcpy setup  or create .mcp_services.yaml", style="dim"
            )
            yield Static(no_profiles_text)
            return

        # Display each profile
        for profile_id in profile_config.list_profiles():
            profile = profile_config.get_profile(profile_id)
            if not profile or not profile.mcps:
                continue

            # For now, show first MCP server in profile
            mcp = profile.mcps[0]

            yield MCPStatus(
                profile_name=profile.name,
                profile_id=profile_id,
                mcp_url=mcp.mcp_url,
                connected=False,  # Will be updated by connection check
                tool_count=0,
                resource_count=0,
                prompt_count=0,
            )

    def _compose_actions(self) -> ComposeResult:
        """Compose quick actions menu."""
        actions = [
            ("1", "Run Tests", "Run test suite against MCP"),
            ("2", "Explore Tools", "Browse available MCP tools"),
            ("3", "Chat Mode", "Interactive chat with tool calling"),
            ("4", "Optimize Docs", "AI-powered docs improvement"),
            ("5", "Configuration", "Manage settings and profiles"),
        ]

        for key, title, description in actions:
            action_text = Text()
            action_text.append(f"  [{key}] ", style="cyan bold")
            action_text.append(f"{title:<25}", style="white")
            action_text.append(f"{description}", style="dim")
            yield Static(action_text, classes="action-item")

    def _compose_activity(self) -> ComposeResult:
        """Compose recent activity log."""
        # Placeholder activity items
        activity_text = Text()
        activity_text.append("  No recent activity", style="dim")
        yield Static(activity_text, classes="activity-item")

    def action_refresh(self) -> None:
        """Refresh the home screen."""
        self.notify("Refreshing...", timeout=2)
        # TODO: Implement actual refresh logic
        # This would check connection status of profiles

    def on_mount(self) -> None:
        """Handle screen mount."""
        # TODO: Start background task to check MCP connections
        pass
