# Chat Interface Quick Start

## Installation

```bash
pip install 'testmcpy[tui]'
```

## Launch

```bash
testmcpy chat
```

## Key Bindings

| Key    | Action           |
|--------|------------------|
| Enter  | Send message     |
| Ctrl+E | Evaluate         |
| Ctrl+S | Save as test     |
| Ctrl+C | Exit             |

## Example Session

1. Launch: `testmcpy chat --profile prod`
2. Type: "Create a bar chart showing sales by region"
3. Watch tool calls execute in real-time
4. Press Ctrl+S to save as test
5. Test file created in tests/ directory

## Tool Call Display

```
🔧 Calling: generate_chart
   dataset_id: "sales.regional"
   config: {...}

✓ Success (2.1s)
  Chart: https://example.com/charts/123
```

## Status Bar

Shows:
- Connection: 🟢 Connected
- Model: claude-haiku-4-5
- Cost: $0.0234
- Messages: 6

## More Info

- Full docs: docs/CHAT_INTERFACE.md
- Help: testmcpy chat --help
- Diagnostics: testmcpy doctor
