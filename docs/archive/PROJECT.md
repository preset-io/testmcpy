# testmcpy - Beautiful CLI Dashboard for MCP Testing 🧪

## Vision: Modern TUI Experience for MCP Testing

Transform testmcpy into a **beautiful, interactive CLI dashboard** that CLI nerds will love just as much as our web UI. Think "k9s" for Kubernetes, "lazygit" for Git, but for MCP testing and benchmarking.

## 🎯 Core Principle: CLI/UI Parity

**Everything in the web UI should have a beautiful CLI equivalent.**
- Same features, same power, different interface
- Code reuse through shared backend logic
- DRY principles - business logic in one place

## ✅ Current Implementation Status

### **Phase 1: COMPLETE - Foundation**
- ✅ **Modern CLI Architecture**: Typer + Rich with beautiful cyan branding
- ✅ **Basic Commands**: `serve`, `test`, `version`, `config`
- ✅ **Web UI Server**: FastAPI backend with React frontend
- ✅ **MCP Profile Management**: YAML-based multi-environment support
- ✅ **Test Execution**: Run tests from CLI with evaluators

### **Phase 1.5: PARTIAL - Current State**
**What Works:**
- ✅ CLI can run individual tests with `testmcpy test <file>`
- ✅ Web UI has full dashboard experience
- ✅ Configuration management via `testmcpy config`
- ✅ Server mode with `testmcpy serve`

**What's Missing:**
- ❌ No interactive TUI dashboard mode
- ❌ No live MCP connection status display
- ❌ No interactive test browser/runner in CLI
- ❌ No chat mode in CLI
- ❌ No MCP explorer in CLI
- ❌ Limited visual feedback (just basic progress bars)

## 🚀 Phase 2: Interactive TUI Dashboard (PLANNED)

### **Primary Command: `testmcpy dash`**

Beautiful interactive dashboard with multiple views:

```bash
testmcpy dash                    # Launch interactive dashboard
testmcpy dash --profile prod     # Launch with specific MCP profile
testmcpy dash --auto-refresh     # Auto-refresh connection status
```

### **Dashboard Views**

#### **1. Home View** (Default)
```
╔═══════════════════════════════════════════════════════════════════════════╗
║ testmcpy - MCP Testing Framework                          v0.2.4 │ 🟢 Live ║
╠═══════════════════════════════════════════════════════════════════════════╣
║                                                                             ║
║  ▀█▀ █▀▀ █▀ ▀█▀ █▀▄▀█ █▀▀ █▀█ █▄█                                         ║
║   █  ██▄ ▄█  █  █ ▀ █ █▄▄ █▀▀  █                                          ║
║                                                                             ║
║  🧪 Test  •  📊 Benchmark  •  ✓ Validate                                   ║
║                                                                             ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ MCP Profiles                                        [p] Profiles [c] Chat  ║
╟─────────────────────────────────────────────────────────────────────────────╢
║  ● prod:Production Workspace             🟢 Connected                      ║
║    https://workspace.example.com/mcp                                       ║
║    Tools: 15 │ Resources: 3 │ Prompts: 2                                   ║
║                                                                             ║
║  ○ sandbox:Sandbox Environment           🔴 Not connected                  ║
║    https://sandbox.example.com/mcp                                         ║
║    [Space] Connect                                                          ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ Quick Actions                          [t] Tests [e] Explorer [?] Help     ║
╟─────────────────────────────────────────────────────────────────────────────╢
║  [1] Run Tests                    Run test suite against MCP               ║
║  [2] Explore Tools               Browse available MCP tools                ║
║  [3] Chat Mode                   Interactive chat with tool calling        ║
║  [4] Optimize Docs               AI-powered docs improvement               ║
║  [5] Configuration               Manage settings and profiles              ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ Recent Activity                                                             ║
╟─────────────────────────────────────────────────────────────────────────────╢
║  ✓ 2 mins ago  test_chart_creation.yaml          3/3 passed │ $0.0234     ║
║  ✗ 5 mins ago  test_dashboard_query.yaml         1/2 passed │ $0.0156     ║
║  ✓ 12 mins ago test_dataset_validation.yaml      5/5 passed │ $0.0445     ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

#### **2. MCP Explorer View** (`e` or `testmcpy explore`)
```
╔═══════════════════════════════════════════════════════════════════════════╗
║ MCP Explorer - prod:Production Workspace                [h] Home [/] Search║
╠═══════════════════════════════════════════════════════════════════════════╣
║ Tools (15)                   │ generate_chart                              ║
╟──────────────────────────────┼─────────────────────────────────────────────╢
║ ▸ Charts & Dashboards    [7]│ Create and save a chart in Superset.       ║
║   > generate_chart       [*]│                                             ║
║     create_dashboard         │ IMPORTANT BEHAVIOR:                         ║
║     update_chart             │ - Charts ARE saved by default               ║
║     delete_chart             │ - Set save_chart=False for preview only    ║
║                              │ - LLM clients MUST display chart URL        ║
║ ▸ Datasets               [5]│                                             ║
║     list_datasets            │ VALIDATION:                                 ║
║     create_dataset           │ - 5-layer pipeline with XSS/SQL injection   ║
║     update_dataset           │ - Column existence validation               ║
║                              │ - Aggregate function compatibility          ║
║ ▸ SQL & Queries          [3]│                                             ║
║     execute_sql              │ Returns:                                    ║
║     saved_queries            │ - Chart ID and metadata (if saved)          ║
║     query_history            │ - Preview URL and explore URL               ║
║                              │ - Detailed validation errors                ║
╟──────────────────────────────┼─────────────────────────────────────────────╢
║ [Enter] Details  [t] Test  [o] Optimize Docs  [g] Generate Test            ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

#### **3. Test Runner View** (`t` or `testmcpy tests`)
```
╔═══════════════════════════════════════════════════════════════════════════╗
║ Test Manager                                           [r] Run [n] New     ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ Test Files (12)              │ test_chart_creation.yaml                    ║
╟──────────────────────────────┼─────────────────────────────────────────────╢
║ ✓ test_chart_creation   [3/3]│ Tests: 3 │ Last run: 2 mins ago            ║
║ ✗ test_dashboard_query  [1/2]│ Status: ✓ PASSED                            ║
║ ✓ test_dataset_valid    [5/5]│ Cost: $0.0234 │ Duration: 4.2s             ║
║ ○ test_new_workflow    [0/0]│                                             ║
║ ✓ test_sql_execution   [2/2]│ Evaluators:                                 ║
║                              │  ✓ was_mcp_tool_called                      ║
║                              │  ✓ execution_successful                     ║
║ [Filter: All ▼]              │  ✓ final_answer_contains                    ║
║  ○ All (12)                  │                                             ║
║  ✓ Passed (10)               │ Details:                                    ║
║  ✗ Failed (1)                │ Tool: generate_chart                        ║
║  ○ Not Run (1)               │ Expected: chart creation success            ║
║                              │ Result: Chart created with ID 3628          ║
║                              │                                             ║
╟──────────────────────────────┼─────────────────────────────────────────────╢
║ [Enter] Run  [e] Edit  [d] Delete  [Space] Select                          ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

#### **4. Chat Mode** (`c` or `testmcpy chat`)
```
╔═══════════════════════════════════════════════════════════════════════════╗
║ Chat - prod:Production Workspace         claude-haiku-4-5 │ Cost: $0.0523 ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ You: Create a chart showing revenue by month                               ║
║                                                                             ║
║ Assistant: I'll create a revenue chart for you.                            ║
║                                                                             ║
║ 🔧 Calling: generate_chart                                                 ║
║    dataset_id: "core.revenue"                                              ║
║    config:                                                                  ║
║      chart_type: "xy"                                                       ║
║      x: {name: "month", aggregate: null}                                   ║
║      y: [{name: "revenue", aggregate: "SUM"}]                              ║
║      kind: "bar"                                                            ║
║                                                                             ║
║ ✓ Success (2.3s)                                                            ║
║   Chart created: https://preset.io/charts/3628                             ║
║   Preview: [View in browser]                                               ║
║                                                                             ║
║ Here's your revenue chart! I've created a bar chart showing monthly        ║
║ revenue totals. You can view it at the link above.                         ║
║                                                                             ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ [Ctrl+C] Cancel  [Ctrl+E] Evaluate  [Ctrl+S] Save as Test                  ║
║ Type your message... ▊                                                      ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

#### **5. Configuration View** (`testmcpy config edit`)
```
╔═══════════════════════════════════════════════════════════════════════════╗
║ Configuration                                        [s] Save [q] Quit     ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ LLM Settings                                                                ║
╟─────────────────────────────────────────────────────────────────────────────╢
║  Default Provider      [anthropic ▼]                                       ║
║  Default Model         [claude-haiku-4-5 ▼]                                ║
║  API Keys              [Configure →]                                        ║
║                                                                             ║
║ MCP Profiles                                              [+] Add Profile  ║
╟─────────────────────────────────────────────────────────────────────────────╢
║  ● prod:Production Workspace                                 [✓] Default   ║
║     URL: https://workspace.example.com/mcp                                 ║
║     Auth: JWT Dynamic                                                       ║
║                                                                             ║
║  ○ sandbox:Sandbox Environment                                             ║
║     URL: https://sandbox.example.com/mcp                                   ║
║     Auth: JWT Dynamic                                                       ║
║                                                                             ║
║ Advanced Settings                                                           ║
╟─────────────────────────────────────────────────────────────────────────────╢
║  Test Timeout          [30s]                                               ║
║  Max Retries          [3]                                                  ║
║  Enable Caching       [✓]                                                  ║
║  Log Level            [INFO ▼]                                             ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

### **Key TUI Features**

#### **Navigation**
- Arrow keys for movement
- Tab/Shift-Tab between panels
- Vim keybindings (hjkl) optional
- Number keys for quick actions
- `/` for search anywhere

#### **Visual Indicators**
- 🟢 Green for connected/passing
- 🔴 Red for disconnected/failing
- 🟡 Yellow for warnings
- ⚪ Gray for inactive
- Spinners for loading states
- Progress bars for long operations

#### **Real-time Updates**
- Live connection status monitoring
- Test execution progress streaming
- Cost tracking updates
- Auto-refresh on config changes

## 🎨 CLI/UI Parity Matrix

| Feature | Web UI | CLI | TUI Dashboard |
|---------|--------|-----|---------------|
| **MCP Profile Management** | ✅ | ✅ | 🎯 Planned |
| **MCP Connection Status** | ✅ | ❌ | 🎯 Planned |
| **Tool Explorer** | ✅ | ❌ | 🎯 Planned |
| **Tool Documentation** | ✅ | ❌ | 🎯 Planned |
| **Optimize Docs (AI)** | ✅ | ❌ | 🎯 Planned |
| **Test Creation** | ✅ | ✅ | 🎯 Planned |
| **Test Execution** | ✅ | ✅ | ✅ |
| **Test Results** | ✅ | ✅ | 🎯 Enhanced |
| **Chat Interface** | ✅ | ❌ | 🎯 Planned |
| **Chat History** | ✅ | ❌ | 🎯 Planned |
| **Configuration** | ✅ | ✅ | 🎯 Enhanced |
| **Live Metrics** | ✅ | ❌ | 🎯 Planned |

## 🏗️ Technical Architecture

### **Shared Backend Logic**

```python
# Current: Duplication
# testmcpy/server/api.py - FastAPI endpoints
# testmcpy/cli.py - CLI commands

# Future: DRY Pattern
# testmcpy/core/
#   ├── mcp_manager.py       # MCP connection management
#   ├── test_runner.py       # Test execution (already exists!)
#   ├── tool_discovery.py    # Tool exploration
#   ├── chat_session.py      # Chat management
#   └── docs_optimizer.py    # LLM docs optimization

# testmcpy/server/api.py - Thin wrapper around core
# testmcpy/cli.py - Thin wrapper around core
# testmcpy/tui/ - Beautiful interface around core
```

### **TUI Tech Stack**

**Option 1: Textual (Recommended)**
- Modern Python TUI framework
- Declarative CSS-like styling
- Rich integration built-in
- Reactive components
- Best for complex layouts

**Option 2: Rich Layout**
- Already using Rich
- Good for simpler dashboards
- More manual layout management
- Lower learning curve

**Option 3: Prompt Toolkit**
- Lower level, more control
- Better for chat interfaces
- Steeper learning curve

**Recommendation: Start with Textual**
- Production-ready
- Beautiful out of the box
- Used by Ollama, Homebrew
- Great documentation

### **Code Organization**

```
testmcpy/
├── core/               # Shared business logic
│   ├── mcp_manager.py
│   ├── test_runner.py (exists)
│   ├── tool_discovery.py
│   ├── chat_session.py
│   └── docs_optimizer.py
├── server/            # Web UI backend
│   └── api.py (thin wrapper around core)
├── tui/               # Terminal UI (NEW)
│   ├── app.py         # Main Textual app
│   ├── screens/
│   │   ├── home.py
│   │   ├── explorer.py
│   │   ├── tests.py
│   │   ├── chat.py
│   │   └── config.py
│   └── widgets/
│       ├── mcp_status.py
│       ├── test_list.py
│       └── tool_tree.py
├── cli.py             # CLI commands (thin wrapper)
└── ui/                # React frontend (existing)
```

## 📊 Implementation Phases

### **Phase 2A: Core Refactoring** (1 week)
- Extract shared logic from server/api.py to core/
- Create MCPManager, ToolDiscovery, ChatSession classes
- Ensure CLI and server both use core modules
- Add comprehensive tests for core modules

### **Phase 2B: Basic TUI** (1 week)
- Implement `testmcpy dash` with Textual
- Home screen with MCP profile list and connection status
- Basic navigation between screens
- MCP explorer with tool list

### **Phase 2C: Test Management** (1 week)
- Test list screen with file browser
- Test execution with real-time progress
- Results display with evaluator details
- Test creation wizard

### **Phase 2D: Chat Interface** (1 week)
- Interactive chat screen
- Tool call visualization
- Save conversation as test
- Evaluate mode for chat sessions

### **Phase 2E: Polish & Features** (1 week)
- Configuration editing in TUI
- LLM docs optimization in TUI
- Keyboard shortcuts guide
- Theme customization
- Auto-refresh modes

## 🎯 Success Metrics

**Developer Experience:**
- ✅ CLI nerds choose TUI over web UI for daily work
- ✅ Zero context switching between terminal and browser
- ✅ Faster workflows with keyboard navigation
- ✅ Better for SSH/remote work scenarios

**Code Quality:**
- ✅ Business logic shared between CLI/TUI/Web UI
- ✅ DRY principles enforced
- ✅ Test coverage for core modules >90%
- ✅ Type safety with mypy

**Feature Parity:**
- ✅ All web UI features available in TUI
- ✅ TUI has unique advantages (keyboard navigation, less resource intensive)
- ✅ Consistent UX across all interfaces

## 🚀 Inspiration & References

### **Excellent CLI Dashboards to Learn From**
- **k9s** - Kubernetes TUI (Textual-like experience)
- **lazygit** - Beautiful git TUI with panels
- **lazydocker** - Docker management TUI
- **btop** - System monitor with gorgeous visuals
- **sup** - Our own Superset CLI (Rich tables, filtering)

### **Key Patterns to Adopt**
1. **Vim-style keybindings** (hjkl navigation)
2. **Panel-based layouts** (multiple simultaneous views)
3. **Live updates** (real-time status monitoring)
4. **Filter/search everywhere** (/ to search)
5. **Context-aware help** (? for help in any screen)
6. **Status bar** (persistent info at bottom)
7. **Color coding** (semantic colors for status)

## 💡 Unique TUI Advantages

### **Why TUI > Web UI Sometimes**

**Performance:**
- Instant startup (no server needed)
- Lower memory footprint
- Works over SSH/slow connections

**Workflow:**
- Never leaves terminal
- Keyboard-first navigation
- Better for automation/scripting
- Easy to pipe output

**Developer Experience:**
- Feels more "native" to CLI users
- Better integration with terminal tools
- Can be used in tmux/screen sessions
- More "hackable" feeling

### **TUI-Exclusive Features** (Ideas)

```bash
# Watch mode - continuous test execution
testmcpy dash --watch tests/

# Tail mode - follow test execution in real-time
testmcpy tail test_chart_creation.yaml

# Quick mode - minimal UI for fast operations
testmcpy quick --run tests/ --filter passing

# Compact mode - for smaller terminals
testmcpy dash --compact

# Export dashboard state
testmcpy dash --export dashboard-state.json
```

## 🎨 Brand Consistency

**Colors:**
- Primary: Cyan (`[cyan]`) - testmcpy brand color
- Success: Green (`[green]`)
- Error: Red (`[red]`)
- Warning: Yellow (`[yellow]`)
- Info: Blue (`[blue]`)
- Dim: Gray (`[dim]`)

**Icons:**
- 🧪 Testing
- 📊 Results/Stats
- ✓ Success
- ✗ Failure
- 🔧 Tool calling
- 💬 Chat
- 🔍 Explore
- ⚙️ Config
- 🟢 Connected
- 🔴 Disconnected

## 📝 Next Steps

### **Immediate Actions**
1. Create `testmcpy/core/` directory
2. Extract MCPManager from server/api.py
3. Install Textual: `pip install textual textual-dev`
4. Create basic TUI scaffold
5. Implement home screen

### **Quick Wins**
- `testmcpy profiles` - Interactive profile selector (like `sup workspace use`)
- `testmcpy status` - MCP connection status dashboard
- `testmcpy explore` - Simple tool browser without full TUI

### **Documentation**
- Update README with TUI features
- Create TUI keybindings reference
- Add TUI screenshots/demos
- Document core module architecture

---

**testmcpy represents the perfect marriage of beautiful UIs and powerful CLIs. By creating a TUI that rivals our web interface, we give developers the choice to work however they're most productive - all while maintaining code quality through shared core logic.** 🚀
