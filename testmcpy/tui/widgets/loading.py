"""
Loading states, spinners, and progress indicators for TUI.
"""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Label, LoadingIndicator, ProgressBar, Static


class LoadingSpinner(Container):
    """A loading spinner with optional message."""

    DEFAULT_CSS = """
    LoadingSpinner {
        align: center middle;
        height: auto;
        padding: 2;
    }

    LoadingSpinner LoadingIndicator {
        height: 3;
    }

    LoadingSpinner .loading-message {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(self, message: str = "Loading..."):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        """Compose the loading spinner."""
        yield LoadingIndicator()
        yield Label(self.message, classes="loading-message")


class OperationProgress(Container):
    """Progress indicator for long-running operations."""

    DEFAULT_CSS = """
    OperationProgress {
        height: auto;
        padding: 1;
        background: $surface;
        border: solid $border;
    }

    OperationProgress .operation-title {
        color: $primary;
        bold: true;
        margin-bottom: 1;
    }

    OperationProgress .operation-status {
        color: $text-muted;
        margin-top: 1;
    }

    OperationProgress ProgressBar {
        margin: 1 0;
    }
    """

    def __init__(
        self,
        title: str,
        total: int = 100,
        show_eta: bool = False,
    ):
        super().__init__()
        self.title = title
        self.total = total
        self.show_eta = show_eta
        self._progress = 0

    def compose(self) -> ComposeResult:
        """Compose the operation progress."""
        yield Label(self.title, classes="operation-title")
        yield ProgressBar(total=self.total, show_eta=self.show_eta, id="progress_bar")
        yield Label("Initializing...", classes="operation-status", id="status_label")

    def update_progress(self, current: int, status: str | None = None) -> None:
        """Update the progress bar and status."""
        self._progress = current
        progress_bar = self.query_one("#progress_bar", ProgressBar)
        progress_bar.update(progress=current)

        if status:
            status_label = self.query_one("#status_label", Label)
            status_label.update(status)

    @property
    def progress(self) -> int:
        """Get current progress value."""
        return self._progress


class ConnectionStatus(Static):
    """Widget showing MCP connection status with indicator."""

    DEFAULT_CSS = """
    ConnectionStatus {
        height: auto;
        width: auto;
        padding: 0 1;
    }

    ConnectionStatus .connected {
        color: $success;
    }

    ConnectionStatus .disconnected {
        color: $error;
    }

    ConnectionStatus .connecting {
        color: $warning;
    }
    """

    def __init__(self, profile_name: str = "Unknown", connected: bool = False):
        super().__init__()
        self.profile_name = profile_name
        self.connected = connected

    def render(self) -> str:
        """Render the connection status."""
        if self.connected:
            return f"🟢 {self.profile_name}"
        else:
            return f"🔴 {self.profile_name}"

    def update_status(self, profile_name: str, connected: bool) -> None:
        """Update the connection status."""
        self.profile_name = profile_name
        self.connected = connected
        self.refresh()


class LiveIndicator(Static):
    """Animated 'LIVE' indicator for auto-refresh mode."""

    DEFAULT_CSS = """
    LiveIndicator {
        width: auto;
        height: auto;
        color: $success;
        bold: true;
        padding: 0 1;
    }

    LiveIndicator.pulsing {
        text-style: bold;
    }
    """

    def render(self) -> str:
        """Render the LIVE indicator."""
        return "🔴 LIVE"


class CostTracker(Static):
    """Widget to display accumulated API costs."""

    DEFAULT_CSS = """
    CostTracker {
        width: auto;
        height: auto;
        padding: 0 1;
        color: $warning;
    }

    CostTracker .cost-amount {
        bold: true;
    }
    """

    def __init__(self, cost: float = 0.0):
        super().__init__()
        self.cost = cost

    def render(self) -> str:
        """Render the cost tracker."""
        return f"💰 ${self.cost:.4f}"

    def add_cost(self, amount: float) -> None:
        """Add to the accumulated cost."""
        self.cost += amount
        self.refresh()

    def reset_cost(self) -> None:
        """Reset the cost counter."""
        self.cost = 0.0
        self.refresh()
