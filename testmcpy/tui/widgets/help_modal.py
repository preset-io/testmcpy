"""
Help modal showing keyboard shortcuts and keybindings.
"""

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Grid, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Markdown, Static


HELP_MARKDOWN = """
# testmcpy Keyboard Shortcuts

Press `?` anywhere to show this help guide.

## Global Navigation

| Key | Action |
|-----|--------|
| `h` | Home screen |
| `e` | Explorer (MCP tools) |
| `t` | Tests manager |
| `c` | Chat mode |
| `5` | Configuration |
| `?` | Show this help |
| `/` | Global search |
| `q` | Quit current screen |
| `Ctrl+C` | Quit application |

## Home Screen

| Key | Action |
|-----|--------|
| `1` | Run Tests |
| `2` | Explore Tools |
| `3` | Chat Mode |
| `4` | Optimize Docs |
| `5` | Configuration |
| `p` | Switch Profile |
| `Space` | Connect/Disconnect profile |

## Explorer Screen

| Key | Action |
|-----|--------|
| `↑↓` / `j k` | Navigate tools |
| `Enter` | View tool details |
| `t` | Create test for tool |
| `o` | Optimize tool docs |
| `g` | Generate test |
| `/` | Search tools |
| `h` | Back to home |

## Test Manager

| Key | Action |
|-----|--------|
| `↑↓` / `j k` | Navigate tests |
| `Enter` | Run selected test |
| `e` | Edit test |
| `d` | Delete test |
| `r` | Run all tests |
| `n` | Create new test |
| `Space` | Select/deselect |
| `f` | Filter tests |

## Chat Mode

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Ctrl+E` | Evaluate conversation |
| `Ctrl+S` | Save as test |
| `Ctrl+C` | Cancel current request |
| `↑↓` | Navigate history |
| `Esc` | Clear input |

## Configuration Screen

| Key | Action |
|-----|--------|
| `Tab` | Next field |
| `Shift+Tab` | Previous field |
| `s` | Save changes |
| `q` | Quit (discard changes) |
| `h` | Home (with confirmation) |

## Tips & Tricks

### Vim Keybindings
- Use `j/k` for up/down navigation
- `g/G` for top/bottom (in lists)
- `/` for search anywhere

### Quick Actions
- Number keys `1-5` work on home screen
- `Space` to toggle/select items
- `Enter` to confirm/execute

### Search
- Press `/` anywhere to search
- Searches across tools, tests, chat history
- Use fuzzy matching for quick results

### Customization
- Change theme in Configuration → Advanced Settings
- Themes: Default (Cyan/Dark), Light, High Contrast
- Save preferences for next session

---

**testmcpy** - Beautiful MCP Testing Dashboard
"""


class HelpModal(ModalScreen):
    """Modal screen showing keyboard shortcuts and help."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("q", "dismiss", "Close", priority=True),
        Binding("?", "dismiss", "Close", priority=True),
    ]

    DEFAULT_CSS = """
    HelpModal {
        align: center middle;
    }

    #help_dialog {
        width: 90;
        max-width: 100;
        height: 90%;
        max-height: 100;
        border: thick $primary;
        background: $surface;
    }

    #help_content {
        height: 100%;
        padding: 1;
    }

    #help_header {
        dock: top;
        height: auto;
        background: $primary;
        color: $background;
        padding: 1;
        text-align: center;
    }

    #help_footer {
        dock: bottom;
        height: auto;
        background: $surface;
        padding: 1;
    }

    HelpModal Markdown {
        height: auto;
        padding: 1;
    }

    HelpModal Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the help modal."""
        with Vertical(id="help_dialog"):
            yield Static("Keyboard Shortcuts & Help", id="help_header")

            with VerticalScroll(id="help_content"):
                yield Markdown(HELP_MARKDOWN)

            with Container(id="help_footer"):
                yield Button("Close [Esc]", variant="primary", id="close_btn")

    @on(Button.Pressed)
    def close_modal(self) -> None:
        """Close the help modal."""
        self.dismiss()

    def action_dismiss(self) -> None:
        """Dismiss the modal."""
        self.dismiss()


class ScreenSpecificHelp(Static):
    """Widget showing context-specific help hints."""

    DEFAULT_CSS = """
    ScreenSpecificHelp {
        height: auto;
        background: $surface;
        border: solid $border;
        padding: 1;
        color: $text-muted;
    }

    ScreenSpecificHelp .key {
        color: $primary;
        bold: true;
    }
    """

    def __init__(self, screen_name: str, hints: list[tuple[str, str]]):
        """
        Initialize screen-specific help.

        Args:
            screen_name: Name of the screen
            hints: List of (key, description) tuples
        """
        super().__init__()
        self.screen_name = screen_name
        self.hints = hints

    def render(self) -> str:
        """Render the help hints."""
        hint_text = "  •  ".join([f"[{key}] {desc}" for key, desc in self.hints])
        return f"{self.screen_name}: {hint_text}"


# Pre-defined help hints for different screens
HOME_HINTS = [
    ("1-5", "Quick Actions"),
    ("p", "Profiles"),
    ("?", "Help"),
    ("q", "Quit"),
]

EXPLORER_HINTS = [
    ("Enter", "Details"),
    ("t", "Test"),
    ("o", "Optimize"),
    ("/", "Search"),
    ("h", "Home"),
]

TESTS_HINTS = [
    ("Enter", "Run"),
    ("e", "Edit"),
    ("d", "Delete"),
    ("n", "New"),
    ("r", "Run All"),
]

CHAT_HINTS = [
    ("Enter", "Send"),
    ("Ctrl+E", "Evaluate"),
    ("Ctrl+S", "Save Test"),
    ("Esc", "Clear"),
]

CONFIG_HINTS = [
    ("s", "Save"),
    ("q", "Quit"),
    ("Tab", "Next Field"),
    ("h", "Home"),
]
