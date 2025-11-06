"""
MCP Status widget for displaying profile connection state.
"""

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container
from textual.widget import Widget
from textual.widgets import Static


class MCPStatus(Widget):
    """Widget showing MCP profile connection state and stats."""

    DEFAULT_CSS = """
    MCPStatus {
        height: auto;
        background: $panel;
        border: solid $primary;
        padding: 1;
        margin: 1;
    }
    
    MCPStatus .profile-name {
        color: $accent;
        text-style: bold;
    }
    
    MCPStatus .profile-url {
        color: $text-muted;
        padding-left: 2;
    }
    
    MCPStatus .profile-stats {
        padding-left: 2;
        padding-top: 1;
    }
    
    MCPStatus .connected {
        color: $success;
    }
    
    MCPStatus .disconnected {
        color: $error;
    }
    
    MCPStatus .action-hint {
        color: $text-muted;
        padding-left: 2;
        padding-top: 1;
    }
    """

    def __init__(
        self,
        profile_name: str,
        profile_id: str,
        mcp_url: str,
        connected: bool = False,
        tool_count: int = 0,
        resource_count: int = 0,
        prompt_count: int = 0,
        *args,
        **kwargs,
    ):
        """
        Initialize MCP status widget.

        Args:
            profile_name: Display name of the profile
            profile_id: Profile ID
            mcp_url: MCP service URL
            connected: Connection status
            tool_count: Number of tools available
            resource_count: Number of resources available
            prompt_count: Number of prompts available
        """
        super().__init__(*args, **kwargs)
        self.profile_name = profile_name
        self.profile_id = profile_id
        self.mcp_url = mcp_url
        self.connected = connected
        self.tool_count = tool_count
        self.resource_count = resource_count
        self.prompt_count = prompt_count

    def compose(self) -> ComposeResult:
        """Compose the MCP status widget."""
        container = Container()

        # Profile name and status
        name_text = Text()
        status_icon = "●" if self.connected else "○"
        status_style = "green" if self.connected else "dim"
        name_text.append(f"  {status_icon} ", style=status_style)
        name_text.append(f"{self.profile_id}:", style="bold")
        name_text.append(f"{self.profile_name}", style="bold cyan")

        # Connection status
        if self.connected:
            name_text.append("                 🟢 Connected", style="green")
        else:
            name_text.append("       🔴 Not connected", style="red")

        yield Static(name_text)

        # URL
        url_text = Text()
        url_text.append(f"    {self.mcp_url}", style="dim")
        yield Static(url_text, classes="profile-url")

        # Stats or action hint
        if self.connected:
            stats_text = Text()
            stats_text.append("    Tools: ", style="dim")
            stats_text.append(str(self.tool_count), style="cyan")
            stats_text.append(" │ Resources: ", style="dim")
            stats_text.append(str(self.resource_count), style="cyan")
            stats_text.append(" │ Prompts: ", style="dim")
            stats_text.append(str(self.prompt_count), style="cyan")
            yield Static(stats_text, classes="profile-stats")
        else:
            action_text = Text()
            action_text.append("    [Space] Connect", style="dim")
            yield Static(action_text, classes="action-hint")

    def update_status(
        self,
        connected: bool,
        tool_count: int = 0,
        resource_count: int = 0,
        prompt_count: int = 0,
    ) -> None:
        """Update the connection status and stats."""
        self.connected = connected
        self.tool_count = tool_count
        self.resource_count = resource_count
        self.prompt_count = prompt_count
        # Trigger re-compose
        self.refresh()
