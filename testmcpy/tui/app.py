"""
Main Textual application for testmcpy TUI dashboard.
"""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer

from testmcpy.tui.screens.chat import ChatScreen
from testmcpy.tui.screens.home import HomeScreen


class TestMCPyApp(App):
    """Main testmcpy TUI application."""

    CSS = """
    Screen {
        background: $surface;
    }
    
    /* Cyan brand colors */
    .brand {
        color: $accent;
    }
    
    .success {
        color: $success;
    }
    
    .error {
        color: $error;
    }
    
    .warning {
        color: $warning;
    }
    
    /* Status indicators */
    .status-connected {
        color: #00ff00;
    }
    
    .status-disconnected {
        color: #ff0000;
    }
    
    .status-pending {
        color: #ffff00;
    }
    
    /* Borders */
    Container {
        border: solid $primary;
    }
    
    Panel {
        border: solid $accent;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("h", "switch_screen('home')", "Home"),
        Binding("e", "switch_screen('explorer')", "Explorer"),
        Binding("t", "switch_screen('tests')", "Tests"),
        Binding("c", "switch_screen('chat')", "Chat"),
        Binding("?", "help", "Help"),
    ]

    SCREENS = {
        "home": HomeScreen,
    }

    TITLE = "testmcpy - MCP Testing Framework"
    SUB_TITLE = "🧪 Test • 📊 Benchmark • ✓ Validate"

    def __init__(self, profile: str | None = None, enable_auto_refresh: bool = False, **kwargs):
        """
        Initialize TestMCPy TUI app.

        Args:
            profile: MCP profile to use
            enable_auto_refresh: Enable auto-refresh of status
        """
        super().__init__(**kwargs)
        self.profile = profile
        self.enable_auto_refresh = enable_auto_refresh

    def on_mount(self) -> None:
        """Handle app mount event."""
        # Update subtitle if profile is set
        if self.profile:
            self.sub_title = f"Profile: {self.profile}"
        # Switch to home screen
        self.push_screen("home")

    def compose(self) -> ComposeResult:
        """Compose the app layout."""
        yield Footer()

    def action_switch_screen(self, screen_name: str) -> None:
        """Switch to a different screen."""
        if screen_name in self.SCREENS:
            self.push_screen(screen_name)
        else:
            self.notify(f"Screen '{screen_name}' not yet implemented", severity="warning")

    def action_help(self) -> None:
        """Show help information."""
        help_text = """
        Keyboard Shortcuts:
        
        q - Quit application
        h - Home screen
        e - Explorer (coming soon)
        t - Tests (coming soon)
        c - Chat (coming soon)
        ? - Show this help
        """
        self.notify(help_text.strip(), timeout=10)

    def set_profile(self, profile: str) -> None:
        """Set the active MCP profile."""
        self.profile = profile
        self.sub_title = f"Profile: {profile}"


def launch_chat(
    profile: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    mcp_url: str | None = None,
):
    """
    Launch the chat interface.

    Args:
        profile: MCP profile ID
        provider: LLM provider
        model: Model name
        mcp_url: MCP service URL
    """
    class ChatApp(App):
        """Simple app wrapper for chat screen."""

        TITLE = "testmcpy - Chat Interface"
        SUB_TITLE = "MCP Testing Framework"

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.profile = profile
            self.provider = provider
            self.model = model
            self.mcp_url = mcp_url

        def on_mount(self) -> None:
            """Initialize the app."""
            self.push_screen(
                ChatScreen(
                    profile=self.profile,
                    provider=self.provider,
                    model=self.model,
                    mcp_url=self.mcp_url,
                )
            )

    app = ChatApp()
    app.run()
