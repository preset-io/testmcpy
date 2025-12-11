# MCP Testing Framework Context

## Project Overview
testmcpy is a comprehensive testing framework for validating LLM tool calling capabilities with MCP (Model Context Protocol) services. It enables developers to test, benchmark, and compare how well different LLMs (Claude, GPT-4, Llama, etc.) interact with MCP tools, ensuring they call the right tools with correct parameters.

**Key Use Cases:**
- Test and validate MCP service implementations
- Compare LLM model performance for tool calling accuracy
- Prevent regressions in MCP integrations through CI/CD
- Optimize costs by finding the best price/performance balance
- Validate parameter passing and tool selection logic

## Key Design Principles

### Cost Consciousness
The system is designed to work primarily with cost-effective options:
- Local LLMs via Ollama (llama3.1:8b, mistral-nemo, qwen2.5:7b)
- Free/local inference engines (Ollama is the default)
- Minimal external API dependencies
- Token usage tracking and cost optimization features

### Architecture
- **Modular Design**: Core functionality is separated into distinct modules (mcp_client.py, llm_integration.py, test_runner.py)
- **Provider Abstraction**: Support for multiple LLM providers (Anthropic, OpenAI, Ollama) through a unified interface
- **Evaluation Framework**: Comprehensive set of evaluators for different test scenarios including deep parameter validation
- **Dual Interface**: CLI (typer + rich) and optional web UI (FastAPI + React)
- **Profile Management**: Multi-environment support with `.mcp_services.yaml` for dev/staging/prod configurations

## Project Structure
```
testmcpy/
├── testmcpy/
│   ├── src/                    # Core framework modules
│   │   ├── mcp_client.py      # MCP protocol client implementation
│   │   ├── llm_integration.py # LLM provider abstraction layer
│   │   └── test_runner.py     # Test execution engine
│   ├── evals/                  # Evaluation functions
│   │   └── base_evaluators.py # Standard evaluators for test validation
│   ├── server/                 # FastAPI web server (modular)
│   │   ├── api.py             # Main FastAPI app (~700 lines, down from 4,400)
│   │   └── routers/           # API route modules
│   │       ├── auth.py        # Authentication flows and debugging
│   │       ├── llm.py         # LLM provider management
│   │       ├── mcp_profiles.py # MCP profile CRUD operations
│   │       ├── test_profiles.py # Test profile management
│   │       ├── tests.py       # Test execution endpoints
│   │       └── tools.py       # MCP tool operations
│   ├── cli/                    # CLI package (modular, ~100 lines main)
│   │   ├── __init__.py        # CLI entry point, imports all commands
│   │   ├── app.py             # Shared app setup (console, enums, defaults)
│   │   └── commands/          # CLI command modules
│   │       ├── mcp.py         # profiles, status, explore-cli
│   │       ├── run.py         # research, run, generate, smoke-test
│   │       ├── server.py      # init, setup, serve, config-cmd, config-mcp, doctor
│   │       ├── tools.py       # tools, export
│   │       └── tui.py         # dash, explore, chat, interact
│   ├── tui/                    # Textual TUI components
│   ├── ui/                     # React web interface
│   ├── mcp_profiles.py         # MCP profile configuration management
│   └── config.py              # Multi-source configuration management
├── tests/                     # Test case definitions (YAML/JSON)
├── docs/                      # Documentation
│   ├── logos/                # Brand assets (SVG, ASCII)
│   ├── MCP_PROFILES.md       # Profile configuration guide
│   └── EVALUATOR_REFERENCE.md # Complete evaluator documentation
├── examples/                  # Example test suites and configurations
└── reports/                   # Generated test reports
```

## Core Components

### MCP Client (`src/mcp_client.py`)
Handles communication with MCP services, including:
- Tool discovery and listing
- Tool execution with parameter validation
- Error handling and retries
- Protocol compliance
- Support for multiple authentication types (bearer, JWT, OAuth)

### LLM Integration (`src/llm_integration.py`)
Provides unified interface for different LLM providers:
- Anthropic (Claude) - recommended for best tool-calling accuracy
- OpenAI (GPT-4) - good alternative with wide compatibility
- Ollama integration for local models (free, privacy-friendly)
- Custom model configurations
- Token usage tracking and cost calculation
- Rate limiting and retry logic

### Test Runner (`src/test_runner.py`)
Orchestrates test execution:
- YAML/JSON test case parsing
- Test execution workflow with progress tracking
- Result collection and detailed reporting
- Evaluation pipeline with pass/fail status
- Token usage and performance metrics
- Support for multiple MCP profiles

### Evaluators (`evals/base_evaluators.py`)
Standard evaluation functions including:
- `was_mcp_tool_called`: Verify specific MCP tools were invoked
- `tool_called_with_parameter`: Check specific parameter was passed
- `tool_called_with_parameters`: Validate multiple parameters at once
- `parameter_value_in_range`: Ensure numeric parameters are within bounds
- `tool_call_sequence`: Validate multi-step tool calling workflows
- `execution_successful`: Check for successful test completion
- `final_answer_contains`: Validate response content
- `within_time_limit`: Performance validation
- `token_usage_reasonable`: Cost/efficiency checks

### MCP Profile Management (`mcp_profiles.py`)
Multi-environment configuration system:
- YAML-based profile definitions (`.mcp_services.yaml`)
- Support for multiple MCP servers per profile
- Environment variable substitution for secrets
- Default profile selection for CLI and web UI
- Authentication configuration (bearer, JWT, OAuth)
- Per-profile timeouts and rate limits

### Configuration Management (`config.py`)
Hierarchical configuration loading:
1. Command-line options (highest priority)
2. MCP Profile from `.mcp_services.yaml`
3. `.env` file in current directory
4. `~/.testmcpy` user config file
5. Environment variables
6. Built-in defaults (lowest priority)

### Web Server & API (`server/api.py`)
FastAPI-based REST API providing:
- `/api/mcp/tools` - List available MCP tools
- `/api/mcp/call-tool` - Execute MCP tool calls
- `/api/chat` - Interactive chat with MCP integration
- `/api/test-files/` - Test file management (CRUD)
- `/api/tests/run` - Execute test suites
- `/api/mcp/optimize-docs` - **NEW: LLM-powered documentation optimization**
- `/api/mcp/profiles` - MCP profile management
- WebSocket support for real-time updates

## Recent Major Features

### LLM Docs Optimization (November 2024)
**NEW Feature**: AI-powered tool documentation improvement
- Endpoint: `/api/mcp/optimize-docs`
- Uses LLM to analyze and improve MCP tool descriptions for better tool-calling accuracy
- Provides clarity score (0-100) and specific improvement suggestions
- Analyzes parameter descriptions, use case clarity, and edge case handling
- Structured output using tool calling for consistent JSON responses
- Integrated into web UI via "Optimize Docs" button in MCP Explorer

**Implementation Details:**
- Uses structured tool calling (`analyze_tool_docs` tool) for reliable JSON output
- Strict validation ensures complete analysis data (score, improvements, optimized_description)
- Supports customizable model/provider selection
- Documentation: `docs/OPTIMIZE_DOCS_QUICKSTART.md`, `docs/OPTIMIZE_DOCS_API.md`

### MCP Profile Management (November 2024)
**Multi-environment configuration system:**
- Define multiple MCP profiles (local, dev, staging, prod) in `.mcp_services.yaml`
- Support for multiple MCP servers per profile
- Environment variable substitution for secure secret management
- Default profile selection with `default: true` flag (auto-selected in web UI)
- CLI flag: `--profile <name>` to switch between environments
- Authentication types: bearer token, JWT (with automatic token refresh), OAuth (planned)

**Benefits:**
- Easily switch between environments without config changes
- Share configuration files with team (secrets in env vars)
- Test against multiple environments in CI/CD
- Per-environment settings (timeouts, rate limits)

### Enhanced Test Results Display (October 2024)
**Improved test runner feedback:**
- Show specific failed evaluator names in test results (not just pass/fail counts)
- Display detailed evaluator information with failure reasons
- Highlight failed evaluators with red styling
- Show evaluator scores as percentages
- Loading spinners and progress indicators during test execution
- Better error handling with detailed error messages

### Web UI Improvements (November 2024)
**Branding and UX enhancements:**
- Added testmcpy logo (SVG and ASCII) to branding
- Logo displayed in web UI sidebar and CLI `--version` output
- Single MCP server selection in Explorer and Chat (prevents tool duplication)
- Info banners showing active MCP server
- Warning banners when multiple servers selected
- Default MCP auto-selection on first load (uses `default: true` flag)
- Retry logic for API calls to handle server startup race conditions

### Tool Call Sequence Evaluator (October 2024)
**New evaluator for multi-step workflows:**
- `tool_call_sequence`: Validate that tools were called in correct order
- Supports exact sequence matching or partial sequence validation
- Useful for testing workflows like: authenticate → query → transform → save
- Documentation in `docs/EVALUATOR_REFERENCE.md`

### Deep Parameter Validation (October 2024)
**Enhanced parameter checking:**
- `tool_called_with_parameter`: Validate single parameter presence and value
- `tool_called_with_parameters`: Validate multiple parameters at once
- `parameter_value_in_range`: Check numeric parameters are within bounds
- Support for nested parameter paths using dot notation
- Comprehensive error messages for debugging

### Codebase Modularization (December 2024)
**Major refactoring for improved maintainability:**

**API Server Modularization:**
- Reduced `api.py` from 4,484 lines to ~700 lines
- Extracted 6 router modules in `server/routers/`:
  - `auth.py`: Authentication flows and debugging endpoints
  - `llm.py`: LLM provider management (11 endpoints)
  - `mcp_profiles.py`: MCP profile CRUD operations (14 endpoints)
  - `test_profiles.py`: Test profile management (5 endpoints)
  - `tests.py`: Test execution endpoints (12 endpoints)
  - `tools.py`: MCP tool operations (5 endpoints)

**CLI Modularization:**
- Created `cli/` package with modular command structure
- `cli/app.py`: Shared setup (console, enums, defaults)
- `cli/commands/` directory with 5 command modules:
  - `mcp.py`: profiles, status, explore-cli
  - `run.py`: research, run, generate, smoke-test
  - `server.py`: init, setup, serve, config-cmd, config-mcp, doctor
  - `tools.py`: tools, export
  - `tui.py`: dash, explore, chat, interact

**Benefits:**
- Easier navigation and code discovery
- Better separation of concerns
- Improved testability (can test modules independently)
- Reduced merge conflicts when working on different features
- Better LLM context utilization (smaller focused files)

## Common Workflows

### For MCP Service Developers
1. **Setup Configuration**: Create `.mcp_services.yaml` with your MCP service URL and auth
2. **Explore Tools**: Run `testmcpy tools` to list available MCP tools
3. **Optimize Documentation**: Use web UI "Optimize Docs" feature to improve tool descriptions
4. **Create Tests**: Define test cases in YAML with prompts and evaluators
5. **Run Tests**: Execute with `testmcpy run tests/ --profile dev`
6. **CI/CD Integration**: Add test execution to GitHub Actions/GitLab CI

### For Testing/Benchmarking LLMs
1. **Configure Multiple Providers**: Set API keys in `~/.testmcpy`
2. **Create Benchmark Suite**: Define tests covering various tool-calling scenarios
3. **Run Against Multiple Models**: Use `--model` flag to test different LLMs
4. **Compare Results**: Analyze pass/fail rates, token usage, and cost metrics
5. **Select Best Model**: Choose optimal model based on accuracy vs. cost

### For Local Development
1. **Use Ollama**: Install Ollama and pull models like `llama3.1:8b`
2. **No API Costs**: Test locally without external API dependencies
3. **Fast Iteration**: Quickly test changes to MCP tools or test definitions
4. **Web UI Development**: Run `testmcpy serve` for visual tool exploration

## Development Practices

### Testing Philosophy
- Focus on real-world MCP tool calling scenarios
- Test different LLM models for capability comparison
- Validate both successful and failure cases
- Measure performance and cost metrics
- Use evaluators to validate tool selection and parameter passing

### Code Quality
- Type hints throughout the codebase (Python 3.10+ required)
- Comprehensive error handling with detailed messages
- Clear separation of concerns (client, LLM, test runner, evaluators)
- Extensive logging for debugging
- Rate limiting and retry logic for API resilience

### Configuration Management
- YAML-based test definitions for version control
- Profile-based environment configurations
- Hierarchical config loading (CLI > profile > env > defaults)
- Environment variable substitution for secrets

## Integration Points

### MCP Service Integration
Works with any MCP service that implements the Model Context Protocol:
- Chart/dashboard creation services (e.g., Superset)
- Data query and transformation tools
- File management and search tools
- API integration services
- Custom business logic tools

### CI/CD Integration
- Run tests in GitHub Actions, GitLab CI, Jenkins
- Use profiles to test against staging/prod environments
- Validate MCP service changes before deployment
- Track LLM performance regressions over time
- Examples in `examples/ci-cd/`

### Local Development
Optimized for local development workflows:
- Ollama support for free, local LLM testing
- No mandatory external API dependencies
- Fast iteration cycles with web UI
- Comprehensive CLI for scripting and automation

## Important Notes

### Best Practices
- **Prefer Ollama for development**: Free, fast, privacy-friendly
- **Use profiles for environments**: Keep dev/staging/prod separate
- **Validate parameters deeply**: Use parameter validation evaluators
- **Optimize tool docs**: Better docs = better LLM tool calling accuracy
- **Track token usage**: Monitor costs across test runs

### Compatibility
- **Python 3.10-3.12** required (3.13+ not yet supported)
- **Backward compatible**: Environment variables and `.env` still work
- **Optional web UI**: Core CLI works without React UI installation

### Security
- **Never commit secrets**: Use environment variables in profiles
- **Use `.gitignore`**: Exclude `.mcp_services.yaml` if it contains sensitive data
- **Share examples only**: Commit `.mcp_services.yaml.example` with placeholders
- **Rotate tokens regularly**: Especially for production environments