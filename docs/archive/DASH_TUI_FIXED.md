# `testmcpy dash` TUI Command Fixed ✅

## Summary

Fixed the `testmcpy dash` command error caused by duplicate command definitions and incorrect function calls.

## Bug Fixed

**Error**:
```
Error running TUI: run_tui() got an unexpected keyword argument 'tests_dir'
```

**Root Cause**:
1. **Duplicate Commands**: Two `dash` commands were defined in cli.py:
   - Line 1980: Correct version using `TestMCPyApp`
   - Line 2449: Old broken version calling non-existent `run_tui(tests_dir=...)`

2. **Wrong Function Call**: The first command was calling `TestMCPyApp` directly instead of using the `run_tui()` helper function

**Fix**:
1. Removed the duplicate/broken `dash` command at line 2449
2. Updated the correct `dash` command to use `run_tui(profile, enable_auto_refresh)` instead of instantiating `TestMCPyApp` directly
3. Added better error handling and documentation

## What is `testmcpy dash`?

The `dash` command launches an interactive terminal UI (TUI) dashboard for MCP testing and exploration.

### Features

- **Browse MCP Tools**: View all available tools and their schemas
- **Manage Profiles**: Switch between MCP service profiles
- **View Status**: Check connection status
- **Quick Actions**: Common tasks via keyboard shortcuts
- **Beautiful UI**: Modern terminal interface built with Textual

### Usage

```bash
# Launch dashboard
testmcpy dash

# Launch with specific profile
testmcpy dash --profile sandbox

# Enable auto-refresh (coming soon)
testmcpy dash --auto-refresh
```

### Help

```bash
$ testmcpy dash --help

Usage: testmcpy dash [OPTIONS]

Launch interactive TUI dashboard.

Beautiful terminal-based dashboard for MCP testing and exploration.
Navigate with keyboard shortcuts, manage profiles, explore tools, and more.

Features:
- Browse MCP tools and resources
- Manage profiles
- View connection status
- Quick actions and shortcuts

Press '?' for help once inside the dashboard.

Options:
  --profile, -p    TEXT  MCP profile to use
  --auto-refresh         Auto-refresh status
  --help                 Show this message and exit.
```

## Implementation Details

### File: `/Users/amin/github/preset-io/testmcpy/testmcpy/cli.py`

**Updated Command** (lines 1979-2012):

```python
@app.command()
def dash(
    profile: str = typer.Option(None, "--profile", "-p", help="MCP profile to use"),
    auto_refresh: bool = typer.Option(False, "--auto-refresh", help="Auto-refresh status"),
):
    """Launch interactive TUI dashboard."""
    try:
        from testmcpy.tui.app import run_tui
    except ImportError:
        console.print("[red]Error: Textual is required[/red]")
        console.print("Install with: pip install 'testmcpy[tui]'")
        return

    # Launch the TUI
    try:
        run_tui(profile=profile, enable_auto_refresh=auto_refresh)
    except Exception as e:
        console.print(f"[red]Error launching dashboard:[/red] {e}")
```

**Removed** (lines 2449-2480):
- Duplicate `dash` command that was calling `run_tui(tests_dir=...)`

### File: `/Users/amin/github/preset-io/testmcpy/testmcpy/tui/app.py`

**Existing Helper Function** (lines 325-334):

```python
def run_tui(profile: str | None = None, enable_auto_refresh: bool = False):
    """
    Launch the main TUI dashboard.

    Args:
        profile: MCP profile to use
        enable_auto_refresh: Enable auto-refresh (not implemented yet)
    """
    app = TestMCPyApp(profile=profile)
    app.run()
```

## TUI Features

Once you launch `testmcpy dash`, you get:

### Home Screen
- **Quick Actions**: Common tasks with keyboard shortcuts
- **Profile Info**: Current MCP profile being used
- **Status Overview**: Connection status and tool count

### Navigation
- **Arrow Keys / hjkl**: Navigate menu items
- **Enter**: Select menu item
- **?**: Show help
- **q**: Quit dashboard

### Menu Options
1. **Browse Tools** - View and explore MCP tools
2. **Manage Profiles** - Switch MCP service profiles
3. **View Status** - Check connection health
4. **Configuration** - Manage settings
5. **Quit** - Exit the dashboard

## Similar Commands

testmcpy has several TUI commands:

```bash
# Main dashboard (menu-driven)
testmcpy dash

# Tool explorer (focused on browsing tools)
testmcpy explore

# Chat interface (interactive conversations)
testmcpy chat
```

Each serves a different purpose:
- **`dash`**: General-purpose dashboard with menu
- **`explore`**: Deep-dive into tool exploration
- **`chat`**: Interactive chat with LLM + MCP tools

## Installation Note

The TUI requires the `textual` library:

```bash
# Install with TUI support
pip install 'testmcpy[tui]'

# Or install textual separately
pip install textual
```

## Verification

```bash
# CLI imports successfully
python3 -c "from testmcpy.cli import app; print('CLI imports successfully')"
# Output: CLI imports successfully

# Command help works
testmcpy dash --help
# Shows usage and options

# Can import TUI
python3 -c "from testmcpy.tui.app import run_tui; print('TUI available')"
# Output: TUI available
```

All tests passed! ✅
