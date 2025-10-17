# Epic: MCP Testing & Validation Framework

## Overview

Build a comprehensive testing and validation framework on top of MCP (Model Context Protocol) to systematically evaluate LLM performance with Superset data operations. This framework would leverage Claude Code as the execution engine and provide structured evaluation capabilities for prompt engineering, model comparison, and MCP service validation.

## Background & Motivation

- ~~Claude Code now works with MCP, enabling `claude -p "{PROMPT}"` as a foundation~~ **UPDATE**: Claude Code currently has bugs with MCP tool calling
- Need systematic approach to test and validate MCP interactions with Superset
- Previous work on simple prompt lists provides starting foundation
- Opportunity to build modern CLI toolkit for LLM+MCP evaluation
- **Alternative approach needed**: Direct LLM integration with MCP protocol

## Technical Approach

### Core Framework Options

1. **Fork promptimize** - Leverage existing evaluation framework
2. **Build new tool** - Create Superset/MCP-specific solution from scratch

### Technology Stack
- **CLI Framework**: typer + rich (modern Python CLI toolkit - following superset-sup patterns)
- **Development Tools**: uv, pre-commit (consistent with Preset ecosystem standards)
- ~~**Execution Engine**: Claude Code via `claude -p` commands~~ **BLOCKED**: MCP tool calling bugs
- **Alternative Execution Engine**: Direct LLM integration (see research options below)
- **Language**: Python (aligns with Superset ecosystem)

### Development Approach
- **Rapid CLI Development**: Leverage Claude Code's exceptional capability for CLI toolkit development
- **Pattern Following**: Use proven patterns from superset-sup for consistency
- **Transformation Strategy**: Consider "big prompt" approach to adapt promptimize for Superset/MCP use case

### Key Features from promptimize
- Duration measurement
- Outcome tracking
- API call counting
- Token usage monitoring
- Multi-model testing
- MCP version compatibility testing

## Architecture & Repository Structure

### Repository Options

**Option A: Monorepo Integration** (Once framework matures)
```
superset/
├── tests/promptimize/           # Experimental location
├── tests/mcp-evals/            # Alternative naming
```

**Option B: Separate Repository** (Recommended for experimentation)
```
superset-promptimize-tests/
├── tests/                      # Test cases
├── evals/                      # Evaluation functions
├── reports/                    # Generated test reports
└── src/                        # Framework code (if needed)
```

### Standard Structure for Promptimize Projects
Each promptimize folder/repo follows consistent pattern:
```
{project-name}/
├── tests/                      # Prompt test cases
├── evals/                      # Evaluation functions
└── reports/                    # Generated test reports
```

## Evaluation System (Evals)

### Generic/Reusable Evaluations
- `was_mcp_tool_called` - Verify MCP tool invocation
- `execution_successful` - Check for errors/exceptions
- `final_answer_contains` - Content validation in responses
- `answer_contains_link(links)` - Link validation
- `within_time_limit` - Performance evaluation
- `token_usage_reasonable` - Cost efficiency

### Superset-Specific Evaluations
- `was_superset_chart_created` - Chart generation validation
- `dashboard_contains_expected_charts` - Dashboard composition
- `sql_query_syntactically_valid` - SQL generation quality
- `dataset_properly_filtered` - Filter application correctness
- `permissions_respected` - Security validation

### Evaluation Strategy Approach
**V1 Focus**: Tool call validation and final answer content analysis
- Most evaluations can be based on MCP tool calls (deterministic and well-controlled)
- Content validation through `final_answer_contains` patterns
- Integration with existing Superset integration tests where applicable

**Future Considerations**:
- Balance between generic evals (reusable) vs custom evals (domain-specific)
- Leverage existing integration test coverage where possible

## Reporting & Versioning

### Report Structure
```
reports/
├── {test_suite_version}_{model}.yml
├── 0.5.1_claude4sonnet.yml
├── 0.5.1_gpt4.yml
└── comparisons/
    └── claude4sonnet_vs_gpt4_v0.5.1.yml
```

### Comparison Metrics
- Success rate
- Execution duration
- Cost analysis
- Failure pattern analysis:
  - Tests that failed in Model A but not Model B
  - Tests that failed in Model B but not Model A

### CLI Commands
```bash
# Run test suite with version tracking
promptimize run --model claude4sonnet --version 0.5.1

# Generate comparison report between models
promptimize report compare reports/0.5.1_claude4sonnet.yml reports/0.5.1_gpt4.yml

# Interactive test development and research
promptimize test --interactive

# Example reports generated
# reports/0.5.1_claude4sonnet.yml
# reports/0.5.1_gpt4.yml
# reports/comparisons/claude4sonnet_vs_gpt4_v0.5.1.yml
```

## Use Cases & Applications

### Development Workflow
- **Interactive Research**: Ad-hoc prompt testing and exploration
- **CI Integration**: Automated testing where it makes sense
- **Model Evaluation**: Systematic comparison across LLM models
- **MCP Service Validation**: Ensure service reliability across versions

### Deployment Contexts
- **Superset Open Source**: Core functionality testing
- **Preset Cloud**: Enterprise-specific scenarios
- **CI/CD Integration**: Selective automation based on impact
- **Local Development**: Interactive testing and iteration

### Superset-Specific Scenarios
- Dashboard generation prompts
- Chart creation workflows
- SQL query generation
- Dataset exploration tasks
- Filter and slice operations

### Preset-Specific Extensions
- Custom deployment scenarios
- Enterprise feature testing
- Performance benchmarking

## Deliverables

### Phase 0: Research & Prototype
- [x] **Research local LLM options with tool calling capabilities** - Selected Ollama + llama3.1:8b
- [ ] **Build minimal Python script for LLM+MCP integration** - Basic testing script exists, FastMCP client needs work
- [x] **Validate tool calling works with selected LLM** - Validated with Superset MCP tools
- [ ] **Performance testing on CPU-only systems** - Basic functionality tested, systematic testing needed

### Phase 1: Foundation
- [x] **Repository setup** - `mcp_testing/` directory structure
- [x] **CLI framework** - CLI with typer + rich
- [x] **Basic test execution engine** - Test runner with YAML configuration
- [x] **Simple report generation** - YAML/JSON reports with comparison
- [ ] **Direct LLM integration** - Basic FastMCP integration exists, needs improvement

### Phase 2: Core Features
- [x] **Multi-model support** - Ollama, OpenAI, and local model providers
- [x] **Versioned test suites** - YAML-based test definitions with metadata
- [x] **Structured reporting** - Reporting with duration, token usage, metrics
- [x] **Comparison utilities** - Model comparison and analysis

### Phase 3: Advanced Capabilities
- [x] **Interactive development mode** - Interactive chat interface: `python cli.py chat`
- [x] **Performance profiling** - Duration measurement, token usage tracking, cost analysis
- [x] **Cost optimization insights** - Local LLM eliminates API costs, performance metrics
- [ ] **Environment abstraction system** - Basic MCP client exists, full abstraction system needed
- [x] **Advanced evaluation capabilities** - Evaluator suite for MCP tool validation
- [ ] **CI/CD integration** - CLI and test runner implemented, CI/CD configuration needed
- [ ] **Advanced mocking capabilities** - Basic evaluation system exists, advanced mocking needed

## Test Environment Architecture

### Environment Types
- **MockedMcpEnvironment**: Unit test equivalent with full mocking
- **LiveSupersetEnvironment**: Integration test equivalent with real Superset instance
- **HybridEnvironment**: Mixed approach for specific testing scenarios

### Mocking Strategy
- **Sophisticated MCP mocked client**: State-aware mock responses
- **State management**: Handle multi-step interactions and dependencies
- **Environment isolation**: Ensure test reproducibility and cleanup

### Testing Levels
- **Unit-style**: Mocked MCP responses, fast execution
- **Integration-style**: Real Superset + MCP service, comprehensive validation
- **Hybrid**: Strategic mix based on test requirements

## Success Metrics

- **Test Coverage**: Comprehensive evaluation of MCP operations
- **Model Insights**: Clear performance differences between LLM models
- **Development Velocity**: Faster prompt iteration and validation
- **Quality Assurance**: Systematic validation of MCP service changes

## Future Opportunities

### Content & Evangelism
- **Blog Posts**: "Building Productively in the Era of MCP" - showcase rapid CLI development
- **Case Studies**: Superset evaluation patterns and MCP integration success stories
- **Open Source**: Generalized LLM+MCP evaluation toolkit (beyond Superset-specific use cases)
- **Developer Experience**: Demonstrate how Claude Code accelerates toolkit development

### Ecosystem Integration
- **Community Adoption**: Framework usable beyond Superset for any MCP-enabled application
- **Vendor Partnerships**: Evaluation standards for MCP providers and service validation
- **Research Applications**: Academic studies on LLM+MCP performance and reliability patterns
- **Industry Standards**: Contribute to MCP evaluation best practices

## Priority & Timeline

**Priority Level**: Medium-High (pending resource allocation discussion)

**Dependencies**:
- ~~Claude Code + MCP stability~~ **BLOCKED**: MCP tool calling bugs
- **NEW**: Local LLM with reliable tool calling capabilities
- Resource allocation for framework development
- Decision on repository structure

**Timeline Estimate**:
- **Phase 0**: Partially complete - Research done, integration needs work
- **Phase 1**: Mostly complete - Foundation solid, FastMCP integration needs refinement
- **Phase 2**: Complete - Core features fully implemented
- **Phase 3**: Partially complete - Basic features done, advanced capabilities need implementation

**Current Status**: Core functionality working, advanced features need development

## Research Phase: Local LLM Options

### Goal
Build functional MCP Testing Framework with FastMCP client integration and local LLM support.

### Research Results

**Selected Solution: Ollama + llama3.1:8b + FastMCP**
- **Model**: `llama3.1:8b` - Basic tool calling functionality validated
- **Integration**: FastMCP client handles MCP protocol
- **Performance**: ~30s response time on macOS ARM64 CPU-only
- **Cost**: $0 - local execution

**Alternative Options Evaluated:**
- **OpenAI-Compatible**: Framework supports OpenAI provider
- **Direct Integration**: Abstraction layer supporting multiple LLM backends

### Implementation Results
Framework components at `mcp_testing/`:
1. **FastMCP Client** - Connection to localhost:5008/mcp/
2. **Tool Validation** - Calls Superset MCP tools
3. **Performance Measurement** - Duration tracking, token usage analysis
4. **Quality Assurance** - Tool call detection and display
5. **CLI Framework** - Interactive chat interface

### Current Capabilities
- LLM tool calling - Basic functionality working
- Response time - Under 30 seconds on test hardware
- Tool calling accuracy - Working on simple tasks
- Framework integration - Structure implemented, some features incomplete

### Phase 4: Anthropic Claude Integration

**Objective**: Add comprehensive support for both Anthropic API and Claude Code CLI through intelligent tool discovery and URL filtering.

#### Background & Motivation
- Claude/Claude Code offers superior tool calling and reasoning capabilities
- Growing demand for Claude-based testing and evaluation
- Need to support both API and CLI usage patterns
- Leverage existing provider abstraction for seamless integration

#### Key Design Constraints
- **URL Protection**: Never send MCP service URLs to external APIs
- **Tool Discovery Abstraction**: Pre-discover tools locally, only send tool schemas to Claude
- **Dual Integration**: Support both Anthropic API (`anthropic` provider) and Claude Code CLI (`claude-cli` provider)
- **Seamless Integration**: Work within existing LLM provider architecture
- **Backwards Compatibility**: No breaking changes to existing test cases or CLI

#### Technical Architecture

**Core Components**:
1. **AnthropicProvider** - Direct API integration with tool schema-only approach
2. **ClaudeCodeProvider** - CLI subprocess integration with prompt injection
3. **ToolDiscoveryService** - Local tool discovery and schema extraction
4. **MCPURLFilter** - Prevent MCP URLs from reaching Anthropic API

**Tool Discovery Flow**:
```
1. Framework connects to MCP service locally
2. Discovers available tools and extracts schemas
3. Creates tool definitions WITHOUT MCP URLs
4. Sends only tool schemas to Claude (never internal URLs)
5. When Claude calls tools, framework executes via local MCP client
6. Returns results to Claude without exposing internal architecture
```

#### Deliverables

**4.1: Core Provider Implementation** ✅ **COMPLETED**
- [x] Create `AnthropicProvider` class in `src/llm_integration.py`
- [x] Implement tool schema extraction (no URL exposure)
- [x] Add proper error handling and token usage tracking
- [x] Integration tests with mock Anthropic API responses

**4.2: Claude Code CLI Integration** ✅ **COMPLETED**
- [x] Create `ClaudeCodeProvider` class for subprocess management
- [x] Implement prompt template system for tool injection
- [x] Add process management and timeout handling
- [x] Support for both `claude -p` and `claude --tools` patterns

**4.3: Tool Discovery Service** ✅ **COMPLETED**
- [x] Create `ToolDiscoveryService` for local MCP tool enumeration
- [x] Implement schema extraction and sanitization (remove internal URLs)
- [x] Add caching for performance optimization
- [x] Tool validation and compatibility checking

**4.4: MCP URL Protection** ✅ **COMPLETED**
- [x] Implement `MCPURLFilter` to prevent URL leakage
- [x] Add logging and monitoring for URL filter triggers
- [x] Runtime validation that no MCP URLs reach Anthropic
- [x] Automated tests to verify URL protection

**4.5: CLI Integration** ✅ **COMPLETED**
- [x] Add `anthropic` and `claude-cli` provider options to CLI
- [x] Update CLI help text and documentation
- [x] Add provider-specific configuration options
- [x] Environment variable support for API keys

**4.6: Advanced Features** ✅ **COMPLETED**
- [x] Streaming response support for Claude Code CLI
- [x] Cost tracking and budget limits for Anthropic API
- [x] Performance comparison between API and CLI modes
- [x] Integration with existing evaluation framework

#### Implementation Steps

**Step 1: Provider Architecture Extension**
```python
# Add to ModelProvider enum in cli.py
claude_api = "anthropic"  # For Anthropic API
claude_cli = "claude-cli"  # For Claude Code CLI

# Add to provider factory in src/llm_integration.py
providers = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "local": LocalModelProvider,
    "anthropic": AnthropicProvider,      # NEW
    "claude-cli": ClaudeCodeProvider,    # NEW
}
```

**Step 2: Tool Discovery Implementation**
```python
class ToolDiscoveryService:
    """Discovers MCP tools locally and creates sanitized schemas."""

    async def discover_tools(self, mcp_url: str) -> List[ToolSchema]:
        """Connect to MCP service and extract tool schemas only."""
        # Connect locally, extract schemas, NEVER expose URLs

    def sanitize_tool_schema(self, tool: MCPTool) -> ToolSchema:
        """Remove any internal URLs or implementation details."""
        # Return only: name, description, parameters
        # NEVER include: URLs, endpoints, internal IDs
```

**Step 3: AnthropicProvider Implementation**
```python
class AnthropicProvider(LLMProvider):
    """Anthropic API provider with MCP URL protection."""

    async def generate_with_tools(self, prompt: str, tools: List[Dict], timeout: float) -> LLMResult:
        # Validate NO MCP URLs in request
        # Send only tool schemas to Anthropic
        # Execute tools locally via MCPClient
        # Return results without exposing internals
```

**Step 4: Claude Code CLI Integration**
```python
class ClaudeCodeProvider(LLMProvider):
    """Claude Code CLI provider via subprocess."""

    async def generate_with_tools(self, prompt: str, tools: List[Dict], timeout: float) -> LLMResult:
        # Create tool-aware prompt template
        # Execute: claude -p "enhanced_prompt_with_tools"
        # Parse tool calls from CLI output
        # Execute tools via local MCP client
```

**Step 5: URL Protection System**
```python
class MCPURLFilter:
    """Ensures no MCP URLs reach external APIs."""

    def validate_request(self, request_data: Dict) -> bool:
        """Return False if any MCP URLs detected."""

    def sanitize_tools(self, tools: List[Dict]) -> List[Dict]:
        """Remove URLs and internal references from tool definitions."""
```

#### Configuration Examples

**Environment Variables**:
```bash
# Optional - only if using Anthropic API
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# Claude Code CLI path (auto-detected if in PATH)
CLAUDE_CLI_PATH=/usr/local/bin/claude
```

**CLI Usage**:
```bash
# Test with Anthropic API (requires API key)
mcp-test research --provider anthropic --model claude-3-5-sonnet-20241022

# Test with Claude Code CLI (requires Claude Code installation)
mcp-test research --provider claude-cli --model claude-3-5-sonnet-20241022

# Run test suite with Claude
mcp-test run tests/ --provider anthropic --model claude-3-5-sonnet-20241022 --output reports/claude_results.yaml
```

**Test Configuration**:
```yaml
# tests/claude_specific_tests.yaml
version: "1.0"
name: "Claude-Specific Test Suite"
description: "Tests optimized for Claude's capabilities"

config:
  providers:
    - name: "anthropic"
      model: "claude-3-5-sonnet-20241022"
      max_cost: 0.50  # Budget protection
    - name: "claude-cli"
      model: "claude-3-5-sonnet-20241022"
      timeout: 45

tests:
  - name: "test_complex_reasoning_with_tools"
    prompt: "Analyze the sales dashboard and create a summary report with key insights, then generate a new chart showing the top performing regions"
    evaluators:
      - name: "was_mcp_tool_called"
      - name: "execution_successful"
      - name: "final_answer_contains"
        args:
          expected_content: ["analysis", "insights", "chart", "regions"]
      - name: "token_usage_reasonable"
        args:
          max_tokens: 4000
          max_cost: 0.10
```

#### Success Criteria ✅ **ALL COMPLETED**

**Functional Requirements**: ✅ **COMPLETED**
- [x] Both `anthropic` and `claude-cli` providers work seamlessly with existing CLI
- [x] Tool discovery works without exposing any MCP URLs to Anthropic
- [x] Tool execution happens locally via existing MCP client
- [x] All existing test cases work unchanged with new providers
- [x] Cost tracking and budget protection for Anthropic API usage

**Security Requirements**: ✅ **COMPLETED**
- [x] MCP URLs NEVER sent to Anthropic API under any circumstances
- [x] Tool schemas sanitized to remove internal implementation details
- [x] Runtime monitoring and alerts for any URL leakage attempts
- [x] Comprehensive test coverage for URL protection mechanisms

**Performance Requirements**: ✅ **COMPLETED**
- [x] Tool discovery cached to avoid repeated MCP connections
- [x] Response times comparable to existing providers
- [x] Minimal overhead for URL filtering and sanitization
- [x] Graceful error handling and fallback mechanisms

**Integration Requirements**: ✅ **COMPLETED**
- [x] No breaking changes to existing codebase
- [x] Seamless integration with evaluation framework
- [x] Compatible with all existing test definitions
- [x] CLI maintains consistent interface across all providers

#### Risk Mitigation

**Risk**: MCP URLs accidentally sent to Anthropic
**Mitigation**: Multi-layer URL filtering with runtime validation and comprehensive tests

**Risk**: Claude Code CLI process management issues
**Mitigation**: Robust subprocess handling, timeouts, and error recovery

**Risk**: High API costs
**Mitigation**: Built-in budget limits, cost tracking, and usage alerts

**Risk**: Performance degradation from tool discovery
**Mitigation**: Aggressive caching and lazy loading of tool schemas

#### Testing Strategy

**Unit Tests**:
- URL filtering effectiveness
- Tool schema sanitization
- Provider initialization and configuration
- Error handling and edge cases

**Integration Tests**:
- End-to-end test execution with both providers
- Tool calling workflow validation
- Cost tracking and budget enforcement
- CLI interface compatibility

**Security Tests**:
- URL leakage detection tests
- Schema sanitization validation
- Runtime monitoring verification
- Penetration testing for URL exposure

#### Phase 4 Timeline

**Week 1: Core Provider Implementation**
- Implement AnthropicProvider with URL protection
- Create ToolDiscoveryService
- Basic CLI integration

**Week 2: Claude Code CLI Integration**
- Implement ClaudeCodeProvider
- Process management and parsing
- Advanced prompt templating

**Week 3: Security & Protection Systems**
- Complete MCPURLFilter implementation
- Comprehensive testing of URL protection
- Runtime monitoring and alerting

**Week 4: Integration & Testing**
- Full CLI integration and testing
- Performance optimization
- Documentation and examples

**Estimated Total: 4 weeks** (compared to 1 day for previous phases due to security complexity)

## Questions & Decisions

1. **Repository Location**: Monorepo vs separate repository?
2. **Framework Choice**: Fork promptimize vs build from scratch?
3. **Resource Allocation**: Priority vs other development efforts?
4. **Integration Strategy**: CI/CD integration requirements?
5. **Open Source Strategy**: Public release timeline and approach?
6. **NEW: LLM Selection**: Which local LLM provides best tool calling + performance balance?
7. **NEW: Claude Integration Priority**: Anthropic API vs Claude Code CLI implementation order?
8. **NEW: Security Validation**: What level of security testing is required for URL protection?