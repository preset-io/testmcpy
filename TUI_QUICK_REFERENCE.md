# testmcpy TUI Quick Reference

## Quick Start

```bash
# Install with TUI support
pip install 'testmcpy[tui]'

# Launch dashboard
testmcpy dash

# Quick commands (no TUI)
testmcpy profiles              # List profiles
testmcpy status                # Check connections
testmcpy explore-cli           # Browse tools
```

## Global Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `?` | Show help |
| `/` | Global search |
| `h` | Home screen |
| `e` | Explorer |
| `5` | Configuration |
| `q` | Quit (with confirmation) |
| `Ctrl+C` | Force quit |
| `F5` | Refresh |

## Screen-Specific Shortcuts

### Home Screen
- `1` - Run Tests
- `2` - Explore Tools
- `3` - Chat Mode
- `4` - Optimize Docs
- `5` - Configuration
- `p` - Switch Profile
- `Space` - Connect/Disconnect

### Explorer
- `↑↓` or `j/k` - Navigate
- `Enter` - View details
- `t` - Create test
- `o` - Optimize docs
- `/` - Search

### Configuration
- `Tab` - Next field
- `Shift+Tab` - Previous field
- `s` - Save changes
- `q` - Quit without saving
- `h` - Home (with confirmation)

## CLI Commands

### Profiles Management
```bash
testmcpy profiles              # List all profiles
testmcpy profiles --details    # Show detailed info
```

### Connection Status
```bash
testmcpy status                # Check all profiles
testmcpy status -p prod        # Check specific profile
```

### Tool Exploration
```bash
testmcpy explore-cli           # Table view
testmcpy explore-cli -o json   # JSON output
testmcpy explore-cli -o yaml   # YAML output
```

## Themes

Three built-in themes available:

1. **Default (Cyan/Dark)** - testmcpy brand colors
2. **Light Mode** - Light background
3. **High Contrast** - Accessibility focused

Change theme in: Configuration → Advanced Settings → Theme

## File Locations

- **User Config**: `~/.testmcpy`
- **MCP Profiles**: `.mcp_services.yaml`
- **Local Config**: `.env` (current directory)
- **Tests**: `tests/` directory

## Tips & Tricks

### Vim-Style Navigation
- Use `j/k` instead of ↑↓
- `g/G` for top/bottom (in lists)
- `/` for search anywhere

### Quick Actions
- Number keys `1-5` work on home screen
- `Space` to toggle/select items
- `Enter` to confirm/execute

### Search
- Press `/` anywhere
- Fuzzy matching for quick results
- Results categorized by type
- `↑↓` to navigate, `Enter` to jump

### Configuration
- Changes tracked automatically
- `s` to save to `~/.testmcpy`
- MCP profiles saved to `.mcp_services.yaml`
- API keys are masked in UI

## Common Workflows

### Setup New Profile
1. Press `5` (Configuration)
2. Scroll to MCP Profiles
3. Click "+ Add Profile"
4. Fill in details
5. Test Connection
6. Save

### Check MCP Status
1. Press `h` (Home)
2. View profile list
3. Or run `testmcpy status`

### Explore Available Tools
1. Press `e` (Explorer)
2. Navigate with ↑↓ or j/k
3. Press `Enter` for details
4. Or run `testmcpy explore-cli`

### Change Theme
1. Press `5` (Configuration)
2. Scroll to Advanced Settings
3. Select Theme dropdown
4. Choose theme
5. Press `s` to save

## Troubleshooting

### TUI Won't Launch
```bash
# Check installation
testmcpy doctor

# Install TUI dependencies
pip install 'testmcpy[tui]'
```

### Can't Connect to MCP
```bash
# Check status
testmcpy status

# Verify config
cat ~/.testmcpy

# Test connection
testmcpy doctor
```

### Missing Features
- Some screens may not be implemented yet
- App will notify and provide alternatives
- Use web UI for full features: `testmcpy serve`

## Getting Help

- Press `?` anywhere in TUI for full help
- Run `testmcpy --help` for CLI help
- Visit: https://github.com/preset-io/testmcpy
- Docs: https://github.com/preset-io/testmcpy/blob/main/docs/

---

**Happy Testing!** 🧪
