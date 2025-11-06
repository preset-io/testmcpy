"""
Error handling modals and dialogs for TUI.
"""

from typing import Callable, Literal

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ErrorModal(ModalScreen):
    """Modal for displaying error messages with optional retry."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("q", "dismiss", "Close", priority=True),
    ]

    DEFAULT_CSS = """
    ErrorModal {
        align: center middle;
    }

    #error_dialog {
        width: 70;
        max-width: 100;
        height: auto;
        border: thick $error;
        background: $surface;
    }

    #error_header {
        dock: top;
        height: auto;
        background: $error;
        color: white;
        padding: 1;
        text-align: center;
    }

    #error_content {
        padding: 2;
    }

    #error_title {
        color: $error;
        bold: true;
        text-align: center;
        margin-bottom: 1;
    }

    #error_message {
        color: $text;
        margin-bottom: 2;
    }

    #error_details {
        background: $background;
        padding: 1;
        border: solid $border;
        color: $dim;
        margin-top: 1;
    }

    #error_buttons {
        height: auto;
        align: center middle;
        margin-top: 1;
    }

    ErrorModal Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        title: str,
        message: str,
        details: str | None = None,
        show_retry: bool = False,
        on_retry: Callable | None = None,
    ):
        super().__init__()
        self.title = title
        self.message = message
        self.details = details
        self.show_retry = show_retry
        self.on_retry = on_retry

    def compose(self) -> ComposeResult:
        """Compose the error modal."""
        with Vertical(id="error_dialog"):
            yield Static("⚠️  Error", id="error_header")

            with Container(id="error_content"):
                yield Label(self.title, id="error_title")
                yield Static(self.message, id="error_message")

                if self.details:
                    yield Static(f"Details:\n{self.details}", id="error_details")

                with Horizontal(id="error_buttons"):
                    if self.show_retry and self.on_retry:
                        yield Button("Retry", variant="primary", id="retry_btn")
                    yield Button("Close", variant="default", id="close_btn")

    @on(Button.Pressed, "#retry_btn")
    def retry_operation(self) -> None:
        """Retry the failed operation."""
        if self.on_retry:
            self.dismiss(True)  # Return True to indicate retry
            self.on_retry()
        else:
            self.dismiss(False)

    @on(Button.Pressed, "#close_btn")
    def close_modal(self) -> None:
        """Close the error modal."""
        self.dismiss(False)

    def action_dismiss(self) -> None:
        """Dismiss the modal."""
        self.dismiss(False)


class WarningModal(ModalScreen):
    """Modal for displaying warning messages."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
    ]

    DEFAULT_CSS = """
    WarningModal {
        align: center middle;
    }

    #warning_dialog {
        width: 60;
        max-width: 100;
        height: auto;
        border: thick $warning;
        background: $surface;
    }

    #warning_header {
        dock: top;
        height: auto;
        background: $warning;
        color: $background;
        padding: 1;
        text-align: center;
    }

    #warning_content {
        padding: 2;
    }

    #warning_title {
        color: $warning;
        bold: true;
        text-align: center;
        margin-bottom: 1;
    }

    #warning_message {
        color: $text;
        margin-bottom: 2;
    }
    """

    def __init__(self, title: str, message: str):
        super().__init__()
        self.title = title
        self.message = message

    def compose(self) -> ComposeResult:
        """Compose the warning modal."""
        with Vertical(id="warning_dialog"):
            yield Static("⚠️  Warning", id="warning_header")

            with Container(id="warning_content"):
                yield Label(self.title, id="warning_title")
                yield Static(self.message, id="warning_message")
                yield Button("OK", variant="primary", id="ok_btn")

    @on(Button.Pressed)
    def close_modal(self) -> None:
        """Close the warning modal."""
        self.dismiss()

    def action_dismiss(self) -> None:
        """Dismiss the modal."""
        self.dismiss()


class ConfirmModal(ModalScreen):
    """Modal for confirmation dialogs."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("y", "confirm", "Yes", priority=True),
        Binding("n", "cancel", "No", priority=True),
    ]

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
    }

    #confirm_dialog {
        width: 60;
        max-width: 100;
        height: auto;
        border: thick $primary;
        background: $surface;
    }

    #confirm_header {
        dock: top;
        height: auto;
        background: $primary;
        color: $background;
        padding: 1;
        text-align: center;
    }

    #confirm_content {
        padding: 2;
    }

    #confirm_title {
        color: $primary;
        bold: true;
        text-align: center;
        margin-bottom: 1;
    }

    #confirm_message {
        color: $text;
        margin-bottom: 2;
        text-align: center;
    }

    #confirm_buttons {
        height: auto;
        align: center middle;
    }

    ConfirmModal Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        title: str,
        message: str,
        confirm_label: str = "Yes",
        cancel_label: str = "No",
        variant: Literal["primary", "error", "warning", "success"] = "primary",
    ):
        super().__init__()
        self.title = title
        self.message = message
        self.confirm_label = confirm_label
        self.cancel_label = cancel_label
        self.variant = variant

    def compose(self) -> ComposeResult:
        """Compose the confirmation modal."""
        with Vertical(id="confirm_dialog"):
            yield Static("❓ Confirm", id="confirm_header")

            with Container(id="confirm_content"):
                yield Label(self.title, id="confirm_title")
                yield Static(self.message, id="confirm_message")

                with Horizontal(id="confirm_buttons"):
                    yield Button(
                        self.confirm_label,
                        variant=self.variant,
                        id="confirm_btn",
                    )
                    yield Button(
                        self.cancel_label,
                        variant="default",
                        id="cancel_btn",
                    )

    @on(Button.Pressed, "#confirm_btn")
    def action_confirm(self) -> None:
        """Confirm the action."""
        self.dismiss(True)

    @on(Button.Pressed, "#cancel_btn")
    def action_cancel(self) -> None:
        """Cancel the action."""
        self.dismiss(False)


class ConnectionErrorModal(ErrorModal):
    """Specialized modal for connection errors."""

    def __init__(
        self,
        profile_name: str,
        error_message: str,
        on_retry: Callable | None = None,
    ):
        super().__init__(
            title=f"Connection Failed: {profile_name}",
            message=f"Could not connect to MCP service.\n\n{error_message}",
            details="Check your network connection and MCP service URL.\nVerify authentication credentials are correct.",
            show_retry=True,
            on_retry=on_retry,
        )


class TestFailureModal(ErrorModal):
    """Specialized modal for test execution failures."""

    def __init__(
        self,
        test_name: str,
        error_message: str,
        show_retry: bool = True,
        on_retry: Callable | None = None,
    ):
        super().__init__(
            title=f"Test Failed: {test_name}",
            message=error_message,
            details="Review test configuration and evaluators.\nCheck MCP service logs for more information.",
            show_retry=show_retry,
            on_retry=on_retry,
        )
