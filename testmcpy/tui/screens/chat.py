"""
Chat interface screen for interactive LLM conversations with tool calling visualization.

This screen provides:
- Real-time chat with LLM
- Tool call visualization
- Cost tracking
- Conversation evaluation
- Test generation from chat history
"""

import json
import time
from pathlib import Path

from rich.console import RenderableType
from rich.json import JSON
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from ...core.chat_session import ChatMessage, ChatSession, ToolCallExecution


class ToolCallWidget(Static):
    """Widget to display a single tool call with expandable details."""

    def __init__(
        self,
        tool_call: ToolCallExecution,
        expanded: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.tool_call = tool_call
        self.expanded = expanded

    def render(self) -> RenderableType:
        """Render the tool call visualization."""
        # Status icon and color
        if self.tool_call.end_time is None:
            status = "⏳"
            color = "yellow"
            status_text = "Running..."
        elif self.tool_call.success:
            status = "✓"
            color = "green"
            status_text = f"Success ({self.tool_call.duration:.1f}s)"
        else:
            status = "✗"
            color = "red"
            status_text = f"Failed ({self.tool_call.duration:.1f}s)"

        # Build the display
        lines = []
        lines.append(f"[bold cyan]🔧 Calling:[/bold cyan] [bold]{self.tool_call.tool_name}[/bold]")

        # Show arguments (formatted)
        if self.tool_call.arguments:
            args_json = json.dumps(self.tool_call.arguments, indent=2)
            if len(args_json) > 200 and not self.expanded:
                # Show abbreviated version
                lines.append("[dim]   Arguments: (press Enter to expand)[/dim]")
                for key in list(self.tool_call.arguments.keys())[:3]:
                    value = self.tool_call.arguments[key]
                    value_str = str(value)
                    if len(value_str) > 50:
                        value_str = value_str[:50] + "..."
                    lines.append(f"[dim]   {key}:[/dim] {value_str}")
                if len(self.tool_call.arguments) > 3:
                    lines.append(f"[dim]   ... and {len(self.tool_call.arguments) - 3} more[/dim]")
            else:
                # Show full arguments
                for line in args_json.split("\n"):
                    lines.append(f"   {line}")

        # Show status
        lines.append(f"\n[{color}]{status} {status_text}[/{color}]")

        # Show result/error if expanded
        if self.expanded and self.tool_call.end_time is not None:
            if self.tool_call.success and self.tool_call.result:
                lines.append("\n[bold]Result:[/bold]")
                result_str = str(self.tool_call.result)
                if len(result_str) > 500:
                    result_str = result_str[:500] + "..."
                lines.append(f"[dim]{result_str}[/dim]")
            elif self.tool_call.error:
                lines.append("\n[bold red]Error:[/bold red]")
                lines.append(f"[red]{self.tool_call.error}[/red]")

        return Panel(
            "\n".join(lines),
            border_style=color,
            padding=(0, 1),
        )


class MessageWidget(Static):
    """Widget to display a chat message."""

    def __init__(self, message: ChatMessage, **kwargs):
        super().__init__(**kwargs)
        self.message = message

    def render(self) -> RenderableType:
        """Render the message."""
        if self.message.role == "user":
            # User message - left-aligned, different color
            content = Text(self.message.content, style="bold yellow")
            return Panel(
                content,
                title="[bold yellow]You[/bold yellow]",
                border_style="yellow",
                padding=(0, 1),
            )
        elif self.message.role == "assistant":
            # Assistant message with tool calls
            content_parts = []

            # Show main response
            if self.message.content:
                content_parts.append(Markdown(self.message.content))

            # Show tool calls
            if self.message.tool_calls:
                for tc in self.message.tool_calls:
                    content_parts.append(ToolCallWidget(tc))

            # Show cost info
            if self.message.cost > 0:
                cost_text = Text(f"\n💰 Cost: ${self.message.cost:.4f}", style="dim cyan")
                if self.message.token_usage:
                    usage = self.message.token_usage
                    cost_text.append(
                        f" | Tokens: {usage.get('total', 0):,} "
                        f"(prompt: {usage.get('prompt', 0):,}, "
                        f"completion: {usage.get('completion', 0):,})",
                        style="dim",
                    )
                content_parts.append(cost_text)

            # Combine all parts
            if len(content_parts) == 1:
                content = content_parts[0]
            else:
                # Create a vertical container for multiple parts
                content = Vertical(*content_parts)

            return Panel(
                content,
                title="[bold cyan]Assistant[/bold cyan]",
                border_style="cyan",
                padding=(0, 1),
            )
        else:
            # System message
            return Panel(
                Text(self.message.content, style="dim"),
                border_style="dim",
                padding=(0, 1),
            )


class ChatScreen(Screen):
    """
    Interactive chat screen with tool calling visualization.

    Key bindings:
    - Enter: Send message (Shift+Enter for newline)
    - Ctrl+C: Cancel current request
    - Ctrl+E: Evaluate conversation
    - Ctrl+S: Save as test
    - Up/Down: Scroll history
    - PgUp/PgDn: Page through history
    - h: Back to home
    - /: Search in history
    """

    CSS = """
    ChatScreen {
        background: $surface;
    }

    #chat-container {
        height: 1fr;
        border: solid $primary;
    }

    #messages-container {
        height: 1fr;
        overflow-y: auto;
        padding: 1;
    }

    #input-container {
        height: auto;
        border-top: solid $primary;
        padding: 1;
    }

    #chat-input {
        width: 100%;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }

    .typing-indicator {
        color: $accent;
        text-style: italic;
    }
    """

    BINDINGS = [
        ("ctrl+e", "evaluate", "Evaluate"),
        ("ctrl+s", "save_test", "Save as Test"),
        ("h", "home", "Home"),
        ("/", "search", "Search"),
        ("ctrl+c", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        profile: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        mcp_url: str | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.chat_session = ChatSession(
            profile=profile, provider=provider, model=model, mcp_url=mcp_url
        )
        self.is_processing = False

    def compose(self) -> ComposeResult:
        """Create the screen layout."""
        yield Header()

        with Container(id="chat-container"):
            with VerticalScroll(id="messages-container"):
                yield Label("Welcome to testmcpy chat! Type a message to begin.", id="welcome")

            with Horizontal(id="input-container"):
                yield Input(
                    placeholder="Type your message... (Enter to send)",
                    id="chat-input",
                )

        yield Static("Initializing...", id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize when screen is mounted."""
        # Initialize chat session
        await self.chat_session.initialize()

        # Update status bar
        self._update_status_bar()

        # Focus input
        self.query_one("#chat-input", Input).focus()

    def _update_status_bar(self) -> None:
        """Update the status bar with session info."""
        status_bar = self.query_one("#status-bar", Static)

        model_text = f"Model: {self.chat_session.model}"
        cost_text = f"Cost: ${self.chat_session.total_cost:.4f}"
        msg_count = self.chat_session.get_message_count()
        msg_text = f"Messages: {msg_count}"

        # Connection status
        conn_status = "🟢 Connected" if self.chat_session._initialized else "🔴 Not Connected"

        status_text = f"{conn_status} | {model_text} | {cost_text} | {msg_text}"
        status_bar.update(status_text)

    @on(Input.Submitted, "#chat-input")
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle message submission."""
        message = event.value.strip()
        if not message or self.is_processing:
            return

        # Clear input
        event.input.value = ""

        # Send message
        await self._send_message(message)

    @work(exclusive=True)
    async def _send_message(self, message: str) -> None:
        """Send a message and display response."""
        self.is_processing = True

        try:
            # Remove welcome message if present
            try:
                welcome = self.query_one("#welcome", Label)
                welcome.remove()
            except:
                pass

            # Add user message to display
            messages_container = self.query_one("#messages-container", VerticalScroll)
            user_msg = ChatMessage(role="user", content=message)
            messages_container.mount(MessageWidget(user_msg))

            # Show typing indicator
            typing_indicator = Label(
                "Assistant is typing...", classes="typing-indicator", id="typing-indicator"
            )
            messages_container.mount(typing_indicator)

            # Scroll to bottom
            messages_container.scroll_end(animate=False)

            # Disable input
            chat_input = self.query_one("#chat-input", Input)
            chat_input.disabled = True

            # Get response from chat session
            response_msg = await self.chat_session.send_message(message)

            # Remove typing indicator
            typing_indicator.remove()

            # Add assistant message to display
            messages_container.mount(MessageWidget(response_msg))

            # Update status bar
            self._update_status_bar()

            # Scroll to bottom
            messages_container.scroll_end(animate=False)

        except Exception as e:
            # Show error message
            error_msg = ChatMessage(
                role="assistant", content=f"Error: {str(e)}", timestamp=time.time()
            )
            messages_container = self.query_one("#messages-container", VerticalScroll)
            try:
                typing_indicator = self.query_one("#typing-indicator")
                typing_indicator.remove()
            except:
                pass
            messages_container.mount(MessageWidget(error_msg))

        finally:
            # Re-enable input
            chat_input = self.query_one("#chat-input", Input)
            chat_input.disabled = False
            chat_input.focus()
            self.is_processing = False

    def action_evaluate(self) -> None:
        """Evaluate the conversation (Ctrl+E)."""
        if not self.chat_session.messages:
            self.notify("No conversation to evaluate", severity="warning")
            return

        # TODO: Implement evaluation modal
        self.notify("Evaluation feature coming soon!", severity="information")

    def action_save_test(self) -> None:
        """Save conversation as a test (Ctrl+S)."""
        if not self.chat_session.messages:
            self.notify("No conversation to save", severity="warning")
            return

        # Generate filename
        timestamp = int(time.time())
        filename = f"test_{timestamp}.yaml"
        filepath = Path("tests") / filename

        try:
            # Save test file (synchronous wrapper)
            import asyncio

            asyncio.create_task(self._save_test_async(str(filepath)))

        except Exception as e:
            self.notify(f"Failed to save test: {e}", severity="error")

    async def _save_test_async(self, filepath: str) -> None:
        """Async helper to save test."""
        try:
            saved_path = await self.chat_session.save_as_test(filepath)
            self.notify(f"Test saved to {saved_path}", severity="information")
        except Exception as e:
            self.notify(f"Failed to save test: {e}", severity="error")

    def action_home(self) -> None:
        """Return to home screen (h)."""
        # TODO: Navigate to home screen when implemented
        self.notify("Navigation coming soon!", severity="information")

    def action_search(self) -> None:
        """Search in conversation history (/)."""
        # TODO: Implement search modal
        self.notify("Search feature coming soon!", severity="information")

    def action_cancel(self) -> None:
        """Cancel current request (Ctrl+C)."""
        if self.is_processing:
            self.notify("Cancellation not yet implemented", severity="warning")
        else:
            self.notify("No request to cancel", severity="information")

    async def on_unmount(self) -> None:
        """Clean up when screen is unmounted."""
        await self.chat_session.close()
