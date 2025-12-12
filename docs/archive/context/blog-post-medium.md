# Testing LLMs with MCP: Why It Matters and How testmcpy Helps

I spent two weeks building an MCP tool for our team. It worked great in testing - Claude called the right tools, passed the right parameters, everything felt smooth. We shipped it.

Three days later someone reported that the tool wasn't working. The LLM was calling a different tool entirely. What changed? Nothing on our end. But somewhere between our testing and production the behavior drifted and we had no way to catch it.

That's when I realized: we need actual tests for this stuff.

## The Problem Nobody's Talking About

Everyone's excited about MCP. Anthropic released it in late 2024 and the ecosystem exploded - hundreds of MCP servers popping up, tools connecting to everything from databases to browsers to internal APIs. But here's what nobody talks about: **how do you test this stuff?**

When you build a traditional API you write unit tests. When you build a web app you write integration tests. But when you build an MCP tool that depends on an LLM to call it correctly... what do you do?

You can't just write `assert tool_called == "my_tool"` because that's not how LLMs work. The model decides what to call based on your prompt and the tool descriptions. And it might decide differently tomorrow, or with a different model, or after you update your tool description.

Most people I talk to are just doing manual testing. They type prompts into Claude Desktop or some chat interface, see if it works, and ship it. That's fine for a prototype but it breaks down fast when you have:

- Multiple tools that need to work together
- Complex parameters that need specific values or ranges
- Performance requirements (can't have tool calls taking 30 seconds)
- Multiple models to support (Claude, GPT-4, local Llama models)
- A team that needs to move fast without breaking things

## Why Testing LLM Tool Calls Is Different

The tricky part about testing MCP integrations is that you're not testing deterministic code. You're testing whether an LLM can figure out what to do based on natural language.

So your tests can't be "when I call function X with parameter Y, I get result Z". Instead they're more like:

- "When a user asks to list datasets, does the LLM call the right tool?"
- "When they ask for the first 10 items, does it pass `page_size=10`?"
- "Does it complete in under 5 seconds?"
- "Does this cost less than a penny per request?"

You're evaluating behavior not just correctness. And that behavior can vary between models so if you want to support multiple LLM providers you need to test them all.

## Enter testmcpy

After hitting this problem one too many times we built testmcpy. It's a testing framework specifically for MCP tools and LLM interactions.

The core idea is simple: **each test is a prompt that should trigger specific tool calls**. You define what you expect to happen, run it against your MCP service with various LLMs, and get a clear pass/fail result.

Here's what a basic test looks like:

```yaml
version: "1.0"
name: "Dataset Operations"

tests:
  - name: "test_list_datasets"
    prompt: "Show me the first 10 datasets"
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "list_datasets"
      - name: "tool_called_with_parameter"
        args:
          tool_name: "list_datasets"
          parameter_name: "page_size"
          parameter_value: 10
      - name: "execution_successful"
      - name: "within_time_limit"
        args:
          max_seconds: 5
```

You run it with:

```bash
testmcpy run tests/ --model claude-haiku-4-5
```

And you get a detailed report showing which evaluators passed or failed, how long it took, how much it cost, and exactly what tool calls were made.

## What Makes It Useful

The key is the evaluators. testmcpy includes a bunch of built-in evaluators for common checks:

**Tool Selection Evaluators:**
- Did the LLM call the right tool?
- Did it call it the right number of times?
- Did it call multiple tools in the right order?

**Parameter Validation Evaluators:**
- Was a specific parameter passed?
- Did it have the right value?
- Was it in a valid range?

**Execution Evaluators:**
- Did the tool call succeed without errors?
- Did it complete within a time limit?
- Does the final answer contain expected content?

**Cost & Performance Evaluators:**
- Token usage tracking
- Cost per request
- Response time

You can combine multiple evaluators on a single test. For example this test checks that the LLM calls the right tool with the right parameters AND that it completes fast enough AND that it doesn't use too many tokens:

```yaml
- name: "test_efficient_query"
  prompt: "List 5 datasets ordered by name"
  evaluators:
    - name: "was_mcp_tool_called"
      args:
        tool_name: "list_datasets"
    - name: "tool_called_with_parameters"
      args:
        tool_name: "list_datasets"
        parameters:
          page_size: 5
          order_column: "name"
        partial_match: true
    - name: "within_time_limit"
      args:
        max_seconds: 3
    - name: "token_usage_reasonable"
      args:
        max_tokens: 1000
    - name: "execution_successful"
```

## Comparing Models

One thing that surprised me was how much model performance varies for tool calling. Some models are great at selecting the right tool but terrible at figuring out the right parameters. Others are expensive but not actually better.

testmcpy makes it easy to run the same test suite against multiple models:

```bash
# Test with Claude Haiku (fast & cheap)
testmcpy run tests/ --model claude-haiku-4-5

# Test with GPT-4 (expensive but accurate)
testmcpy run tests/ --model gpt-4-turbo

# Test with local Llama (free but maybe less accurate)
testmcpy run tests/ --model llama3.1:8b
```

You can compare the results to figure out which model gives you the best price/performance balance for your use case. Maybe Haiku is good enough for 90% of queries and you only need the expensive model for complex multi-step workflows.

## Growth Without Regressions

The real value though is catching regressions. Once you have a test suite you can run it in CI/CD. Every time you change a tool description or add a new tool or update your MCP service you run the tests and make sure nothing broke.

This is huge because MCP tools are weird to test manually. You have to spin up your service, configure an LLM client, type prompts, inspect the tool calls... it's tedious and error-prone. With automated tests you just push code and the CI system tells you if something broke.

We set it up in GitHub Actions:

```yaml
name: MCP Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Install testmcpy
        run: pip install testmcpy
      - name: Run tests
        run: testmcpy run tests/ --model claude-haiku-4-5
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

Now every PR gets tested automatically. If someone's change breaks tool calling we know immediately.

## Real Testing, Real Fast

What I like about testmcpy is that it doesn't try to be magic. It's not doing anything fancy - just sending prompts to LLMs and checking what tools get called. But that's exactly what we needed.

The workflow is:

1. Write tests as YAML files describing prompts and expected behavior
2. Run them against your MCP service with various models
3. Get detailed pass/fail results
4. Iterate on your tools or prompts until tests pass
5. Run in CI to catch regressions

You can also use the interactive chat mode to explore your tools before writing tests:

```bash
testmcpy chat
```

This gives you a chat interface where you can see exactly what tools are being called and what parameters are passed. It's super useful for understanding how the LLM interprets your tool descriptions.

## The Boring Parts Matter

There's a lot of exciting stuff happening in the LLM space right now. New models every week, new capabilities, new frameworks. But if you're actually building production systems with this stuff the boring parts matter:

- Can you test it?
- Can you catch regressions?
- Can you compare models objectively?
- Can you track costs?
- Can you onboard new team members without tribal knowledge?

testmcpy focuses on these boring parts. It's not sexy but it's useful.

## Try It Out

If you're building MCP tools and you've hit the "how do I test this" wall, give testmcpy a shot:

```bash
pip install testmcpy
testmcpy setup
testmcpy chat
```

The setup wizard walks you through configuring your MCP service and LLM provider. Then you can start writing tests or just explore your tools interactively.

It works with Claude (best tool calling accuracy in my testing), GPT-4, and local models via Ollama. You can test with paid APIs for production and use free local models for development.

Check out the repo: [github.com/preset-io/testmcpy](https://github.com/preset-io/testmcpy)

## What's Next

The MCP ecosystem is still young. There's a lot we don't know about best practices for building and testing these tools. But one thing I'm confident about: if we want MCP to work reliably in production we need good testing tools.

testmcpy is our attempt at solving that problem. It's open source, actively maintained, and we use it every day for our own MCP services at Preset.

If you try it out let me know what you think. And if you hit testing challenges we haven't solved yet, open an issue. We're figuring this out as we go and feedback from people actually building with MCP is super valuable.

---

*Built by the team at [Preset](https://preset.io) for testing our Apache Superset MCP integrations and beyond.*