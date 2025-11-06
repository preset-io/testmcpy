# Chat Interface - Interactive LLM Conversations with MCP Tools

The testmcpy chat interface provides a beautiful, interactive terminal UI for chatting with LLMs that have access to MCP tools. All tool calls are visualized in real-time, and conversations can be saved as test files or evaluated using the built-in evaluator system.

## Features

- **Real-time Chat**: Interactive conversations with LLMs
- **Tool Call Visualization**: See exactly when and how tools are called
  - Tool name and arguments displayed
  - Execution time tracking
  - Success/failure status with color coding
  - Expandable details for results and errors
- **Cost Tracking**: Live cost updates in the status bar
- **Conversation Management**:
  - Save conversations as test files (Ctrl+S)
  - Evaluate conversations with evaluators (Ctrl+E)
  - Export conversations to JSON/YAML
  - Clear conversation history
- **Beautiful UI**: Built with Textual for a modern terminal experience
  - Syntax highlighting for code
  - Markdown rendering for responses
  - Rich formatting for tool calls
  - Persistent status bar

## Installation

The chat interface requires the `textual` library:

```bash
# Install with TUI support
pip install 'testmcpy[tui]'

# Or install textual separately
pip install textual
```

## Usage

### Basic Usage

Launch the chat interface with default configuration:

```bash
testmcpy chat
```

The chat interface will:
1. Use your configured LLM provider (from `~/.testmcpy` or `.env`)
2. Connect to your configured MCP service
3. Discover available tools
4. Open an interactive terminal UI

### With Specific Configuration

```bash
# Use a specific MCP profile
testmcpy chat --profile prod

# Use a specific model
testmcpy chat --model claude-opus-4

# Use a specific provider
testmcpy chat --provider openai --model gpt-4

# Use a specific MCP URL
testmcpy chat --mcp-url https://your-mcp-service.com/mcp
```

### Chat Screen Layout

```
╔═══════════════════════════════════════════════════════════╗
║ testmcpy - Chat Interface                                ║
╠═══════════════════════════════════════════════════════════╣
║                                                           ║
║ You: Create a chart showing revenue by month             ║
║                                                           ║
║ Assistant: I'll create a revenue chart for you.          ║
║                                                           ║
║ 🔧 Calling: generate_chart                               ║
║    dataset_id: "core.revenue"                            ║
║    config:                                                ║
║      chart_type: "xy"                                     ║
║      x: {name: "month", aggregate: null}                 ║
║      y: [{name: "revenue", aggregate: "SUM"}]            ║
║                                                           ║
║ ✓ Success (2.3s)                                         ║
║   Chart created: https://preset.io/charts/3628           ║
║                                                           ║
║ Here's your revenue chart! You can view it at the link.  ║
║                                                           ║
║ 💰 Cost: $0.0234 | Tokens: 1,245 (prompt: 890, comp: 355)║
║                                                           ║
╠═══════════════════════════════════════════════════════════╣
║ Type your message... ▊                                    ║
╠═══════════════════════════════════════════════════════════╣
║ 🟢 Connected | Model: claude-haiku-4-5 | Cost: $0.0523   ║
║ Messages: 4                                               ║
╚═══════════════════════════════════════════════════════════╝
```

## Key Bindings

| Key         | Action                                  |
|-------------|-----------------------------------------|
| Enter       | Send message                            |
| Ctrl+E      | Evaluate conversation with evaluators   |
| Ctrl+S      | Save conversation as test file          |
| Ctrl+C      | Cancel current request / Exit           |
| h           | Back to home (when implemented)         |
| /           | Search in history (when implemented)    |
| Up/Down     | Scroll message history                  |
| PgUp/PgDn   | Page through message history            |

## Tool Call Visualization

When an LLM calls a tool, you'll see:

1. **Tool Call Header**: Shows the tool name with a 🔧 icon
2. **Arguments**: Formatted JSON showing the parameters passed
3. **Status Indicator**:
   - ⏳ Running (yellow)
   - ✓ Success (green)
   - ✗ Failed (red)
4. **Execution Time**: Duration in seconds
5. **Result**: Tool output (when expanded)

### Example Tool Call

```
🔧 Calling: generate_chart
   dataset_id: "core.revenue"
   config:
     chart_type: "xy"
     x: {name: "month", aggregate: null}
     y: [{name: "revenue", aggregate: "SUM"}]
     kind: "bar"

✓ Success (2.3s)
  Chart created: https://preset.io/charts/3628
  Preview: [View in browser]
```

## Saving Conversations as Tests

Press **Ctrl+S** to save your conversation as a test file:

1. The first user message becomes the test prompt
2. All tool calls are extracted as expected tool calls
3. Default evaluators are added:
   - `was_mcp_tool_called`: Ensures tools were called
   - `execution_successful`: Ensures tools succeeded
4. Test is saved to `tests/test_<timestamp>.yaml`

### Generated Test Example

```yaml
name: test_1699564800
prompt: Create a chart showing revenue by month
model: claude-haiku-4-5
provider: anthropic
expected_tool_calls:
  - tool: generate_chart
    arguments:
      dataset_id: core.revenue
      config:
        chart_type: xy
        x:
          name: month
          aggregate: null
        y:
          - name: revenue
            aggregate: SUM
evaluators:
  - type: was_mcp_tool_called
    params: {}
  - type: execution_successful
    params: {}
metadata:
  created_from_chat: true
  timestamp: 1699564800
  total_cost: 0.0523
  message_count: 4
```

## Evaluating Conversations

Press **Ctrl+E** to evaluate your conversation with evaluators:

- Runs all configured evaluators on the conversation
- Shows which evaluators passed/failed
- Displays scores and failure reasons
- Helps validate LLM behavior

**Note**: Full evaluation UI coming in future updates. Currently shows a placeholder notification.

## Status Bar

The status bar at the bottom shows:

- **Connection Status**: 🟢 Connected / 🔴 Not Connected
- **Model**: Current LLM model in use
- **Cost**: Cumulative cost for the session
- **Messages**: Total message count

## Programmatic Usage

You can also use the chat interface components programmatically:

```python
import asyncio
from testmcpy.core.chat_session import ChatSession

async def main():
    # Create a chat session
    session = ChatSession(
        profile="prod",
        provider="anthropic",
        model="claude-haiku-4-5"
    )

    # Initialize
    await session.initialize()

    # Send a message
    response = await session.send_message(
        "Create a chart showing revenue by month"
    )

    # Check response
    print(f"Response: {response.content}")
    print(f"Tool calls: {len(response.tool_calls)}")
    print(f"Cost: ${response.cost:.4f}")

    # Export conversation
    json_export = session.export_conversation("json")

    # Save as test
    test_path = await session.save_as_test("tests/my_test.yaml")

    # Clean up
    await session.close()

asyncio.run(main())
```

## Architecture

The chat interface follows the DRY principle with shared business logic:

```
testmcpy/
├── core/
│   └── chat_session.py       # Business logic (CLI/TUI/Web UI agnostic)
├── tui/
│   ├── app.py                # TUI application entry point
│   ├── screens/
│   │   └── chat.py           # Chat screen UI
│   └── widgets/
│       ├── MessageWidget     # Chat message display
│       └── ToolCallWidget    # Tool call visualization
└── cli.py                    # CLI command registration
```

### Core Components

1. **ChatSession** (`core/chat_session.py`):
   - Manages conversation history
   - Handles LLM integration
   - Executes MCP tool calls
   - Tracks costs and tokens
   - Exports/saves conversations

2. **ChatScreen** (`tui/screens/chat.py`):
   - Textual-based UI
   - Real-time message display
   - Input handling
   - Key binding management

3. **MessageWidget** & **ToolCallWidget**:
   - Rich formatting for messages
   - Tool call visualization
   - Expandable details

## Troubleshooting

### Chat command not found

Make sure you have the latest version:

```bash
pip install --upgrade testmcpy
```

### Textual not installed

Install TUI dependencies:

```bash
pip install 'testmcpy[tui]'
```

### Connection errors

Check your configuration:

```bash
testmcpy doctor
```

Ensure MCP service is running and accessible:

```bash
testmcpy tools --mcp-url YOUR_MCP_URL
```

### Tool calls not working

1. Verify MCP service has tools: `testmcpy tools`
2. Check authentication is configured
3. Try with `--profile` to use a specific profile
4. Check logs for detailed error messages

## Future Enhancements

- [ ] Full evaluation modal with detailed results
- [ ] Search in conversation history
- [ ] Streaming responses for real-time updates
- [ ] Multi-turn conversation with context
- [ ] Tool call editing and retry
- [ ] Conversation templates
- [ ] Integration with home screen navigation

## Related Commands

- `testmcpy test` - Run saved test files
- `testmcpy tools` - List available MCP tools
- `testmcpy setup` - Configure testmcpy
- `testmcpy doctor` - Health check and diagnostics

## See Also

- [PROJECT.md](../PROJECT.md) - Full TUI roadmap
- [MCP_PROFILES.md](MCP_PROFILES.md) - MCP profile management
- [README.md](../README.md) - Main documentation
