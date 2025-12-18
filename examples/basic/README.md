# Basic Examples

This directory contains simple example test files to help you get started with testmcpy.

## Files

### simple_tool_test.yaml
A minimal test case demonstrating basic MCP tool calling validation. This is the best starting point for new users.

**What it covers:**
- Basic tool invocation checking
- Response content validation
- Performance testing

**Run it:**
```bash
testmcpy run examples/basic/simple_tool_test.yaml --model claude-haiku-4-5
```

### multi_evaluator_test.yaml
A comprehensive example showing how to combine multiple evaluators for thorough testing.

**What it covers:**
- Tool selection verification
- Parameter validation
- Multi-step workflows
- Token usage monitoring
- Error handling

**Run it:**
```bash
testmcpy run examples/basic/multi_evaluator_test.yaml --model claude-haiku-4-5
```

## Getting Started

1. **Configure testmcpy:**
   ```bash
   testmcpy setup
   ```

2. **View available tools:**
   ```bash
   testmcpy tools
   ```

3. **Run a basic test:**
   ```bash
   testmcpy run examples/basic/simple_tool_test.yaml
   ```

4. **Customize for your MCP service:**
   - Copy one of these examples
   - Update the `tool_name` values to match your MCP service's tools
   - Modify the prompts to test your specific use cases
   - Add or remove evaluators based on your needs

## Customizing Tests

### Changing Tool Names

Replace `list_datasets` with your actual MCP tool names:

```yaml
- name: "was_mcp_tool_called"
  args:
    tool_name: "your_tool_name"  # Change this
```

### Testing Different Models

Test the same suite with different LLM providers:

```bash
# Anthropic Claude
testmcpy run examples/basic/simple_tool_test.yaml --model claude-haiku-4-5

# OpenAI GPT
testmcpy run examples/basic/simple_tool_test.yaml --model gpt-4-turbo --provider openai

# Local Ollama
testmcpy run examples/basic/simple_tool_test.yaml --model llama3.1:8b --provider ollama
```

### Adding More Evaluators

See the [Evaluator Reference](../../docs/EVALUATOR_REFERENCE.md) for all available evaluators:

- `was_mcp_tool_called` - Check if a specific tool was invoked
- `execution_successful` - Verify no errors occurred
- `final_answer_contains` - Validate response content
- `within_time_limit` - Ensure reasonable performance
- `token_usage_reasonable` - Monitor API costs
- `tool_called_with_parameter` - Validate parameters
- `parameter_value_in_range` - Check parameter values
- `tool_call_count` - Count tool invocations

## Next Steps

1. **Advanced Examples:** Check out [../ci-cd/](../ci-cd/) for CI/CD integration examples
2. **Full Documentation:** See [docs/CLIENT_USAGE_GUIDE.md](../../docs/CLIENT_USAGE_GUIDE.md)
3. **Custom Evaluators:** Learn how to write your own evaluators in [CONTRIBUTING.md](../../CONTRIBUTING.md)
4. **Test Your MCP Service:** Create a `tests/` directory in your MCP service repository and add test cases

## Tips

- Start with `simple_tool_test.yaml` and gradually add complexity
- Use `testmcpy research` to explore what your LLM can do
- Run tests against multiple models to compare behavior
- Set up CI/CD to catch regressions early
- Monitor token usage to optimize costs
- Test both success and error scenarios

## Questions?

- Read the [README](../../README.md)
- Check [GitHub Discussions](https://github.com/preset-io/testmcpy/discussions)
- Open an [issue](https://github.com/preset-io/testmcpy/issues) for bugs or feature requests
