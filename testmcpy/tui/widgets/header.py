"""
Header widget displaying testmcpy logo, version, and status.
"""

from rich.text import Text
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from testmcpy import __version__


class Header(Widget):
    """Header widget with logo, version, and connection status."""

    DEFAULT_CSS = """
    Header {
        height: auto;
        background: $panel;
        padding: 1;
        border: solid $accent;
    }
    
    #logo {
        text-align: center;
        color: $accent;
    }
    
    #status-line {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
    }
    """

    def __init__(
        self,
        profile: str | None = None,
        connected: bool = False,
        *args,
        **kwargs,
    ):
        """
        Initialize header widget.

        Args:
            profile: Active MCP profile name
            connected: Connection status
        """
        super().__init__(*args, **kwargs)
        self.profile = profile
        self.connected = connected

    def compose(self) -> ComposeResult:
        """Compose header layout."""
        # Logo
        logo_text = Text()
        logo_text.append("  ▀█▀ █▀▀ █▀ ▀█▀ █▀▄▀█ █▀▀ █▀█ █▄█\n", style="bold cyan")
        logo_text.append("   █  ██▄ ▄█  █  █ ▀ █ █▄▄ █▀▀  █ \n", style="bold cyan")
        logo_text.append("\n  🧪 Test  •  📊 Benchmark  •  ✓ Validate", style="dim")

        yield Static(logo_text, id="logo")

        # Status line
        status_text = self._build_status_text()
        yield Static(status_text, id="status-line")

    def _build_status_text(self) -> Text:
        """Build status line text."""
        text = Text()

        # Version
        text.append(f"v{__version__}", style="dim")
        text.append(" │ ", style="dim")

        # Profile
        if self.profile:
            text.append(f"Profile: {self.profile}", style="cyan")
            text.append(" │ ", style="dim")

        # Connection status
        if self.connected:
            text.append("🟢", style="")
            text.append(" Connected", style="green")
        else:
            text.append("🔴", style="")
            text.append(" Disconnected", style="red")

        return text

    def update_status(self, connected: bool) -> None:
        """Update connection status."""
        self.connected = connected
        status_widget = self.query_one("#status-line", Static)
        status_widget.update(self._build_status_text())

    def update_profile(self, profile: str) -> None:
        """Update active profile."""
        self.profile = profile
        status_widget = self.query_one("#status-line", Static)
        status_widget.update(self._build_status_text())
