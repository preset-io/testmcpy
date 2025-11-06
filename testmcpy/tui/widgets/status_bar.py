"""
Status bar widget showing current context and key hints.
"""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Footer, Label, Static


class StatusBar(Footer):
    """
    Enhanced status bar showing current screen, profile, and context-specific key hints.

    Replaces the default footer with a more informative status bar.
    """

    DEFAULT_CSS = """
    StatusBar {
        background: $surface;
        color: $text;
        height: 1;
        dock: bottom;
    }

    StatusBar .screen-name {
        color: $primary;
        bold: true;
    }

    StatusBar .profile-name {
        color: $success;
    }

    StatusBar .separator {
        color: $dim;
    }

    StatusBar .key-hint {
        color: $text-muted;
    }
    """

    def __init__(
        self,
        screen_name: str = "Home",
        profile_name: str | None = None,
        hints: list[tuple[str, str]] | None = None,
    ):
        super().__init__()
        self.screen_name = screen_name
        self.profile_name = profile_name
        self.hints = hints or []

    def render(self) -> str:
        """Render the status bar."""
        parts = [self.screen_name]

        if self.profile_name:
            parts.append(f"│ {self.profile_name}")

        if self.hints:
            hint_text = "  ".join([f"[{key}] {desc}" for key, desc in self.hints])
            parts.append(f"│ {hint_text}")

        return "  ".join(parts)

    def update_status(
        self,
        screen_name: str | None = None,
        profile_name: str | None = None,
        hints: list[tuple[str, str]] | None = None,
    ) -> None:
        """Update the status bar content."""
        if screen_name is not None:
            self.screen_name = screen_name
        if profile_name is not None:
            self.profile_name = profile_name
        if hints is not None:
            self.hints = hints
        self.refresh()


class SimpleStatusBar(Static):
    """Simpler status bar for showing just text."""

    DEFAULT_CSS = """
    SimpleStatusBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    """

    def __init__(self, text: str = ""):
        super().__init__(text)
        self.status_text = text

    def update_text(self, text: str) -> None:
        """Update status bar text."""
        self.status_text = text
        self.update(text)
