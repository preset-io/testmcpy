"""
Super simple working TUI - just the essentials.
"""

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, Static, Label
from textual.binding import Binding


class SimpleTUI(App):
    """Minimal working TUI for testmcpy."""

    CSS = """
    Screen {
        align: center middle;
    }

    .title {
        text-align: center;
        text-style: bold;
        color: cyan;
        width: 100%;
        padding: 1;
    }

    .menu-item {
        width: 100%;
        padding: 1;
        background: $panel;
        margin: 1;
    }

    .menu-item:hover {
        background: $accent;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("1", "screen_1", "Explorer"),
        Binding("2", "screen_2", "Tests"),
        Binding("3", "screen_3", "Chat"),
    ]

    TITLE = "testmcpy"

    def __init__(self, profile: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.profile = profile

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        yield Header()
        yield Container(
            Label("🧪 testmcpy - MCP Testing Framework", classes="title"),
            Label(""),
            Label("Press 1: 🔍 Explorer - Browse MCP Tools", classes="menu-item"),
            Label("Press 2: 🧪 Tests - Run Tests", classes="menu-item"),
            Label("Press 3: 💬 Chat - Interactive Chat", classes="menu-item"),
            Label(""),
            Label("Press q to quit", classes="menu-item"),
        )
        yield Footer()

    def action_screen_1(self) -> None:
        """Explorer placeholder."""
        self.notify("Explorer coming soon - use 'testmcpy tools' CLI for now")

    def action_screen_2(self) -> None:
        """Tests placeholder."""
        self.notify("Tests coming soon - use 'testmcpy run' CLI for now")

    def action_screen_3(self) -> None:
        """Chat placeholder."""
        self.notify("Chat coming soon - use 'testmcpy chat' CLI for now")


def run_tui(profile: str | None = None, **kwargs):
    """Launch the TUI."""
    app = SimpleTUI(profile=profile)
    app.run()
