# testmcpy TUI - Interactive Terminal UI

Beautiful, keyboard-driven interface for exploring and testing MCP services.

## Features

### MCP Explorer (`testmcpy explore`)

Interactive tool browser with:

- **Split Layout**: Tree view on left, detailed info on right
- **Categorized Tools**: Organized by Charts, Datasets, SQL, etc.
- **Real-time Search**: Filter tools as you type
- **Detailed Schemas**: View complete parameter documentation
- **Quick Actions**: Generate tests, optimize docs, AI assistance

### Key Bindings

#### Navigation
- `Arrow Keys` / `hjkl` - Navigate tree
- `Enter` - Expand/collapse or show details
- `Tab` - Switch between panels
- `/` - Focus search
- `Esc` - Clear search / Return to home

#### Actions
- `t` - Generate test file for selected tool
- `o` - Optimize documentation (AI-powered)
- `g` - Generate test with AI
- `r` - Refresh tools from MCP
- `h` - Return to home
- `q` - Quit

### Tool Categories

Tools are automatically categorized:

1. **Charts & Dashboards** - Chart/viz creation and management
2. **Datasets** - Dataset/table operations
3. **SQL & Queries** - SQL execution and query tools
4. **Other** - Miscellaneous tools

### Tool Details

The right panel shows:

- Full tool description
- Parameter list with types
- Required vs optional parameters
- Complete JSON schema
- Parameter descriptions

### Actions

#### Generate Test (`t`)

Creates a YAML test file in `tests/` directory with:
- Test template
- Tool name pre-filled
- Basic evaluators configured

#### Optimize Docs (`o`)

Uses LLM to improve tool documentation:
- Clearer descriptions
- Better parameter explanations
- Actionable suggestions
- Shows cost and token usage

#### AI Test Generation (`g`)

Coming soon: AI-powered test generation based on tool schema.

## Usage

### Launch Explorer

```bash
# Use default profile
testmcpy explore

# Use specific profile
testmcpy explore --profile prod
```

### With MCP Profiles

Configure profiles in `.mcp_services.yaml`:

```yaml
default: local-dev

profiles:
  local-dev:
    name: "Local Development"
    mcps:
      - name: "Preset Superset"
        mcp_url: "http://localhost:5008/mcp"
        auth:
          type: "none"

  production:
    name: "Production"
    mcps:
      - name: "Preset Cloud"
        mcp_url: "https://workspace.preset.io/mcp"
        auth:
          type: "jwt"
          api_url: "https://api.app.preset.io/v1/auth/"
          api_token: "${PRESET_API_TOKEN}"
          api_secret: "${PRESET_API_SECRET}"
```

## Architecture

### Directory Structure

```
testmcpy/tui/
├── app.py              # Main TUI application
├── screens/            # Screen components
│   ├── home.py        # Home dashboard
│   ├── explorer.py    # Tool explorer
│   └── ...
└── widgets/           # Reusable widgets
    ├── tool_tree.py   # Categorized tool tree
    └── ...
```

### Core Integration

The TUI uses shared core modules:

- `core/tool_discovery.py` - Fetch and cache MCP tools
- `core/docs_optimizer.py` - AI-powered doc improvements
- `src/mcp_client.py` - MCP service communication
- `src/llm_integration.py` - LLM provider abstraction

### Caching

Tools are cached after first fetch:
- Press `r` to force refresh
- Cache shared across multiple views
- Reduces API calls and improves responsiveness

## Development

### Running in Dev Mode

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run with textual dev tools
textual run --dev testmcpy/tui/app.py
```

### Testing

The TUI uses Textual's testing framework:

```python
from textual.pilot import Pilot
from testmcpy.tui.app import TestMCPyApp

async def test_explorer():
    async with TestMCPyApp().run_test() as pilot:
        await pilot.press("e")  # Open explorer
        assert pilot.app.screen.title == "MCP Explorer"
```

### Styling

CSS-like styling in `explorer.py`:

```python
CSS = """
#left_panel {
    width: 35%;
    border-right: solid cyan;
}

#right_panel {
    width: 65%;
    padding: 1 2;
}
"""
```

## Troubleshooting

### Textual not installed

```bash
pip install textual
# or
pip install "testmcpy[dev]"
```

### Profile not found

Check `.mcp_services.yaml` exists and has valid profiles:

```bash
testmcpy config-cmd  # View current config
```

### MCP connection failed

Verify MCP URL and authentication:

```bash
testmcpy tools --profile prod  # Test connection
```

### Display issues

Try different terminal emulators:
- iTerm2 (macOS)
- Windows Terminal (Windows)
- Alacritty (Cross-platform)
- Kitty (Cross-platform)

## Future Enhancements

Phase 2 roadmap:

- [ ] Test runner view
- [ ] Chat interface
- [ ] Configuration editor
- [ ] Live MCP connection monitoring
- [ ] Benchmark comparison view
- [ ] Theme customization
- [ ] Export capabilities

## References

- [Textual Documentation](https://textual.textualize.io/)
- [PROJECT.md](../../../PROJECT.md) - Overall vision
- [MCP Profiles Documentation](../../../docs/MCP_PROFILES.md)
