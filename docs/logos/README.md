# testmcpy Logos

Collection of logos and branding assets for testmcpy.

## ASCII Art Logos

See `ascii_logo.txt` for various ASCII art versions that can be used in:
- Terminal output
- CLI help messages
- Documentation
- README files

## SVG Logo

`logo.svg` - Vector logo suitable for:
- Documentation headers
- GitHub social preview
- Website/landing page
- High-resolution displays

### Color Palette

The logo uses a modern, developer-friendly color scheme:

- **Primary Blue**: `#7aa2f7` - Main brand color
- **Accent Purple**: `#bb9af7` - Gradient accent
- **Success Green**: `#9ece6a` - Validation/success states
- **Background**: `#1a1b26` - Dark background
- **Text Gray**: `#a9b1d6` - Secondary text

## Usage Examples

### In README

```markdown
![testmcpy](docs/logos/logo.svg)

# testmcpy

Test and benchmark LLMs with MCP tools
```

### In CLI Output

```python
from pathlib import Path

logo_path = Path(__file__).parent / "docs" / "logos" / "ascii_logo.txt"
with open(logo_path) as f:
    print(f.read())
```

### As Terminal Welcome Banner

Add to `testmcpy --help` or `testmcpy serve` startup.

## License

Same license as testmcpy (Apache 2.0)
