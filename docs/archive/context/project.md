# Claude Agent SDK Integration Plan for testmcpy

## Overview

This document outlines the migration plan for integrating the [Claude Agent SDK for Python](https://github.com/anthropics/claude-agent-sdk-python) into the testmcpy MCP Testing Framework. The SDK provides a more streamlined and maintainable approach to Claude integration compared to our current manual API implementation.

## Current State Analysis

### What We Have

1. **Manual Anthropic API Integration** (`src/llm_integration.py:585-787`)
   - Direct HTTP client using httpx
   - Custom tool schema conversion and sanitization
   - Manual tool execution flow
   - MCP URL filtering for security
   - Prompt caching implementation

2. **Tool Discovery Service** (`src/llm_integration.py:531-583`)
   - Connects to local MCP services
   - Discovers and caches tool schemas
   - Executes tool calls via MCPClient
   - Sanitizes tool schemas for external APIs

3. **Multi-Provider Architecture**
   - Support for Ollama, OpenAI, local models, Anthropic, and Claude CLI
   - Factory pattern for provider creation
   - Consistent LLMProvider interface

### Current Limitations

- **Maintenance burden**: Managing raw API calls, headers, request formatting
- **Limited tooling**: No built-in hooks or advanced SDK features
- **Verbose code**: ~200 lines for Anthropic provider alone
- **Security complexity**: Manual URL filtering and sanitization
- **No streaming support**: Current implementation doesn't support streaming responses

## Claude Agent SDK Benefits

### What the SDK Provides

1. **Simplified API Interaction**
   - `query()`: Simple async interface for one-off tasks
   - `ClaudeSDKClient`: Advanced client for continuous conversations
   - Built-in streaming support
   - Automatic message formatting

2. **Custom Tools**
   - Decorator-based tool definition (`@tool`)
   - Direct Python function integration
   - Type-safe tool interactions
   - No subprocess management needed

3. **MCP Integration**
   - Native in-process MCP server support
   - Automatic tool discovery
   - Built-in permission controls
   - Real-time progress monitoring

4. **Advanced Features**
   - Hooks for programmatic control
   - Permission mode customization
   - System prompt configuration
   - Tool allowlisting

## Migration Strategy

### Phase 1: Research & Prototyping (1-2 days)

**Goal**: Validate SDK compatibility with current architecture

#### Tasks

1. **Install and explore the SDK**
   ```bash
   pip install claude-agent-sdk
   ```

2. **Create proof-of-concept** (`research/claude_sdk_poc.py`)
   - Test basic `query()` interface
   - Test `ClaudeSDKClient` for multi-turn conversations
   - Validate MCP tool integration
   - Measure performance vs. current implementation

3. **Test MCP integration patterns**
   - Connect SDK to existing MCP service (http://localhost:5008/mcp)
   - Verify tool discovery and execution
   - Test security controls and permissions

4. **Document findings**
   - Performance benchmarks (response time, token usage)
   - Feature comparison matrix
   - Security considerations
   - Breaking changes or limitations

#### Success Criteria

- SDK successfully connects to our MCP service
- Can execute at least 3 different MCP tools
- Performance is comparable or better than current implementation
- No security regressions

### Phase 2: SDK Provider Implementation (2-3 days)

**Goal**: Create new ClaudeSDKProvider alongside existing AnthropicProvider

#### Tasks

1. **Create ClaudeSDKProvider class** (`src/llm_integration.py`)
   ```python
   class ClaudeSDKProvider(LLMProvider):
       """Claude Agent SDK provider with MCP integration."""

       def __init__(self, model: str, mcp_url: str, **kwargs):
           self.model = model
           self.mcp_url = mcp_url
           self.client = None

       async def initialize(self):
           # Initialize SDK client with MCP server
           pass

       async def generate_with_tools(self, prompt, tools, timeout):
           # Use SDK query() or ClaudeSDKClient
           pass
   ```

2. **Implement core functionality**
   - `initialize()`: Set up SDK client with MCP URL
   - `generate_with_tools()`: Use SDK query interface
   - `close()`: Clean up SDK resources
   - Tool schema conversion (SDK format � our format)

3. **Integrate with existing architecture**
   - Add `claude-sdk` to provider factory
   - Maintain LLMProvider interface compatibility
   - Preserve existing test structure
   - Keep security features (URL filtering)

4. **Add configuration support**
   - Environment variables for SDK options
   - CLI flags for SDK-specific features
   - Configuration file support

#### Code Changes

**File**: `src/llm_integration.py`
- Add ClaudeSDKProvider class (~150 lines)
- Update factory function to include `claude-sdk` option
- Add SDK-specific imports

**File**: `cli.py`
- Add `claude-sdk` to ModelProvider enum
- Add SDK-specific CLI options (optional)

**File**: `pyproject.toml`
- Add `claude-agent-sdk` to dependencies

#### Success Criteria

- ClaudeSDKProvider passes all existing tests
- Can run existing test suites with `--provider claude-sdk`
- Feature parity with AnthropicProvider
- No breaking changes to existing code

### Phase 3: Testing & Validation (1-2 days)

**Goal**: Ensure SDK integration is production-ready

#### Tasks

1. **Unit tests** (`tests/test_claude_sdk_provider.py`)
   - Test initialization with valid/invalid credentials
   - Test tool calling with MCP service
   - Test error handling and timeouts
   - Test token usage and cost tracking

2. **Integration tests**
   - Run existing test suites with SDK provider
   - Compare results with AnthropicProvider
   - Test all evaluators work correctly
   - Verify report generation

3. **Performance testing**
   - Benchmark response times
   - Compare token usage
   - Test concurrent requests
   - Measure memory usage

4. **Security validation**
   - Verify MCP URL filtering still works
   - Test permission controls
   - Validate tool schema sanitization
   - Review SDK security features

#### Success Criteria

- All tests pass with SDK provider
- Performance within 10% of current implementation
- No security vulnerabilities
- Documentation updated

### Phase 4: Feature Enhancement (2-3 days)

**Goal**: Leverage SDK-specific features not available in current implementation

#### Potential Enhancements

1. **Streaming Support**
   - Add streaming response handler
   - Update CLI to show streaming output
   - Improve user experience in chat mode

2. **Custom Tools**
   - Create Python-native tools for common operations
   - Add evaluator-as-tool capability
   - Implement tool composition

3. **Hooks System**
   - Add hooks for test execution monitoring
   - Implement pre/post tool-call hooks
   - Add custom logging and metrics

4. **Advanced Permissions**
   - Tool allowlisting per test case
   - Permission mode configuration
   - Rate limiting and quotas

5. **Multi-turn Conversations**
   - Use ClaudeSDKClient for stateful testing
   - Implement conversation history
   - Add context management

#### Success Criteria

- At least 2 new SDK-specific features implemented
- Features documented in README
- Example tests using new features
- User feedback collected

### Phase 5: Migration & Cleanup (1-2 days)

**Goal**: Transition from AnthropicProvider to ClaudeSDKProvider as default

#### Tasks

1. **Update documentation**
   - README with SDK installation and usage
   - Migration guide for existing users
   - SDK-specific configuration examples
   - Update known limitations section

2. **Update defaults**
   - Change default provider to `claude-sdk` in CLI
   - Update environment variable examples
   - Update config templates

3. **Deprecation planning**
   - Mark AnthropicProvider as deprecated
   - Add deprecation warnings
   - Set timeline for removal (e.g., 3 months)
   - Provide migration script if needed

4. **Code cleanup**
   - Remove redundant code
   - Refactor shared utilities
   - Update type hints and docstrings
   - Format and lint

#### Success Criteria

- All documentation updated
- Deprecation plan communicated
- Zero breaking changes for users
- Clean git history with good commit messages

## Implementation Details

### File Structure

```
testmcpy/
   src/
      llm_integration.py        # Add ClaudeSDKProvider class
      mcp_client.py             # Keep as-is (used by SDK too)
      test_runner.py            # Minor updates if needed
   research/
      claude_sdk_poc.py         # NEW: POC and examples
   tests/
      test_claude_sdk.py        # NEW: SDK-specific tests
   pyproject.toml                # Add claude-agent-sdk dependency
   requirements.txt              # Add claude-agent-sdk
   README.md                     # Update with SDK info
   project.md                    # This file
```

### Dependency Changes

**Add to `pyproject.toml`**:
```toml
dependencies = [
    # ... existing deps
    "claude-agent-sdk>=0.1.0",  # Check latest version
]
```

**Add to `requirements.txt`**:
```
claude-agent-sdk>=0.1.0
```

### Configuration Examples

**Environment Variables**:
```bash
# Current
export ANTHROPIC_API_KEY="sk-..."
export MCP_URL="http://localhost:5008/mcp"

# With SDK (same, but with additional options)
export CLAUDE_SDK_SYSTEM_PROMPT="You are a Superset testing assistant"
export CLAUDE_SDK_ALLOWED_TOOLS="Read,Write,Bash"
```

**CLI Usage**:
```bash
# Current
python cli.py run tests/ --provider anthropic --model claude-3-5-sonnet-20241022

# With SDK
python cli.py run tests/ --provider claude-sdk --model claude-3-5-sonnet-20241022

# With SDK-specific features
python cli.py run tests/ --provider claude-sdk --streaming --permissions strict
```

### Key Technical Decisions

1. **Keep both providers initially**
   - Gradual migration reduces risk
   - Users can compare and choose
   - Easier rollback if issues arise

2. **Preserve existing interfaces**
   - No breaking changes to LLMProvider
   - Maintain test case format
   - Keep evaluator system unchanged

3. **Leverage SDK strengths**
   - Use SDK for MCP integration where possible
   - Keep custom security layers (URL filtering)
   - Add SDK-exclusive features incrementally

4. **Maintain security posture**
   - Don't remove existing security checks
   - Add SDK permission controls
   - Review SDK's security model
   - Keep tool schema sanitization

## Risk Assessment

### High Risk

1. **Breaking changes in SDK**
   - *Mitigation*: Pin SDK version, test thoroughly
   - *Fallback*: Keep AnthropicProvider as backup

2. **Performance regression**
   - *Mitigation*: Comprehensive benchmarking
   - *Fallback*: Make SDK optional, use if faster

3. **Security vulnerabilities**
   - *Mitigation*: Security audit, maintain existing filters
   - *Fallback*: Disable SDK provider if critical issues found

### Medium Risk

1. **SDK bugs or instability**
   - *Mitigation*: Extensive testing, report issues upstream
   - *Fallback*: Version pinning, workarounds

2. **Feature gaps**
   - *Mitigation*: Identify gaps in Phase 1
   - *Fallback*: Supplement with direct API calls

3. **Migration complexity**
   - *Mitigation*: Phased approach, good documentation
   - *Fallback*: Extended transition period

### Low Risk

1. **User adoption**
   - *Mitigation*: Clear benefits communication
   - *Fallback*: Keep both options long-term

2. **Documentation lag**
   - *Mitigation*: Update docs in each phase
   - *Fallback*: Community contributions

## Success Metrics

### Technical Metrics

- **Code reduction**: 30-50% less code in Claude provider
- **Performance**: d10% response time difference
- **Test coverage**: e90% for new SDK code
- **Security**: Zero regressions in security tests

### User Metrics

- **Adoption rate**: e50% of tests use SDK within 1 month
- **Bug reports**: <5 critical bugs in first month
- **User feedback**: Positive sentiment from team
- **Documentation**: <3 doc-related issues per week

## Timeline

| Phase | Duration | Start | End |
|-------|----------|-------|-----|
| Phase 1: Research | 1-2 days | Day 1 | Day 2 |
| Phase 2: Implementation | 2-3 days | Day 3 | Day 5 |
| Phase 3: Testing | 1-2 days | Day 6 | Day 7 |
| Phase 4: Features | 2-3 days | Day 8 | Day 10 |
| Phase 5: Migration | 1-2 days | Day 11 | Day 12 |
| **Total** | **7-12 days** | | |

## Next Steps

1. **Review this plan** with the team
2. **Get approval** to proceed
3. **Start Phase 1**: Install SDK and create POC
4. **Schedule check-ins** after each phase
5. **Document learnings** throughout process

## References

- [Claude Agent SDK Python](https://github.com/anthropics/claude-agent-sdk-python)
- [SDK Documentation](https://docs.claude.com/en/docs/claude-code/sdk/sdk-python)
- [MCP Protocol Spec](https://spec.modelcontextprotocol.io/)
- [Current testmcpy README](./README.md)
- [Current LLM Integration](./src/llm_integration.py)

## Questions & Decisions Log

### Open Questions

1. Should we support SDK-specific features in test YAML format?
2. What's the deprecation timeline for AnthropicProvider?
3. Should streaming be enabled by default?
4. How to handle SDK version updates?

### Decisions Made

1.  Use phased approach (not big-bang rewrite)
2.  Keep both providers during transition
3.  Maintain backward compatibility
4.  Start with POC before full implementation

---

## Implementation Status Update

**Date**: 2025-10-02
**Status**: ⚠️ **Partial Implementation - Architecture Mismatch Identified**

### Key Finding

The Claude Agent SDK is designed for **stdio-based MCP servers** (command-line tools that communicate via stdin/stdout), not **HTTP-based MCP services** like the Superset MCP service.

**Architecture Incompatibility:**
- SDK expects: MCP servers spawned as subprocesses with stdio transport
- Our setup: HTTP-based MCP service at `http://localhost:5008/mcp`
- Result: Cannot bridge HTTP → SDK without additional infrastructure

### Implementation Completed

✅ **Phase 1 & 2 Completed**:
- ClaudeSDKProvider class implemented and integrated
- Works for standalone queries (no MCP)
- Factory and CLI updated
- Dependencies added

### Recommendation

**For HTTP-based MCP services (Superset MCP)**:
- ✅ Use `anthropic` provider (fully supported)
- ✅ Already working and tested
- ✅ Proper HTTP MCP integration

**For stdio-based MCP servers** (future):
- ✅ Use `claude-sdk` provider
- Examples: Local file tools, git operations, custom CLI tools
- SDK excels at this use case

### Conclusion

The SDK integration is **valuable but not for this specific use case**. The `anthropic` provider remains the recommended choice for testing with HTTP-based MCP services like Superset.

---

*Last Updated: 2025-10-02*
*Author: Claude (via research and implementation)*
*Status: Implemented with Limitations*