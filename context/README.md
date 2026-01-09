# testmcpy Context

This directory contains modular knowledge files that document testmcpy's concepts, architecture, and best practices. These files are designed to be:

- **Composable** - Load only what you need
- **Self-referencing** - Concepts link to related concepts
- **Version-controlled** - Track evolution of ideas over time
- **AI-friendly** - Agents can load specific concepts as context

## Core Concepts

Stable, foundational knowledge about testmcpy:

- **[architecture.md](concepts/architecture.md)** - System design, data flow, and component overview
- **[evaluators.md](concepts/evaluators.md)** - Built-in evaluators for validating LLM tool calls
- **[test-format.md](concepts/test-format.md)** - YAML test definition format and structure
- **[mcp-profiles.md](concepts/mcp-profiles.md)** - MCP service profile configuration
- **[configuration.md](concepts/configuration.md)** - LLM provider and general configuration
- **[authentication.md](concepts/authentication.md)** - Auth mechanisms (JWT, OAuth, Bearer)
- **[cli.md](concepts/cli.md)** - CLI commands and options reference

## Guides (How-To)

Step-by-step implementation guides:

- **[getting-started.md](guides/getting-started.md)** - Quick start guide
- **[installation.md](guides/installation.md)** - Installation instructions
- **[writing-tests.md](guides/writing-tests.md)** - How to write test suites
- **[custom-evaluators.md](guides/custom-evaluators.md)** - Building custom evaluators
- **[ci-cd-integration.md](guides/ci-cd-integration.md)** - CI/CD setup (GitHub Actions, GitLab CI)
- **[development.md](guides/development.md)** - Development workflow and contributing

## Guidelines

Development standards and best practices:

*(Empty for now - add testing patterns, code style guides as needed)*

## Archives

Historical documentation preserved for reference:

- **[AUTH_FLOW_DIAGRAM.md](archives/AUTH_FLOW_DIAGRAM.md)** - OAuth/JWT flow diagrams
- **[CLIENT_USAGE_GUIDE.md](archives/CLIENT_USAGE_GUIDE.md)** - Original client usage guide
- **[EVALUATOR_REFERENCE.md](archives/EVALUATOR_REFERENCE.md)** - Original evaluator reference

## Usage with AI Agents

When working with AI coding assistants, point them to specific context files:

```
Read context/concepts/evaluators.md for evaluator documentation
Read context/guides/writing-tests.md for test writing examples
```

This keeps prompts focused and reduces token usage compared to loading all documentation at once.

## Lifecycle

Files progress through stages as they mature:

1. **explorations/** - Rough notes, experiments (not yet created)
2. **concepts/** - Validated, stable documentation
3. **archives/** - Completed/deprecated docs preserved for reference
