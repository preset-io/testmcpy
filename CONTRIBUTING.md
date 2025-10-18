# Contributing to testmcpy

Thank you for your interest in contributing to testmcpy! This document provides guidelines and information for contributors.

We welcome contributions of all kinds: bug reports, feature requests, documentation improvements, and code contributions.

## Code of Conduct

Be respectful, inclusive, and collaborative. We're all here to build better tools for the community.

## Development Setup

### Prerequisites
- Python 3.9 or higher (3.9, 3.10, 3.11, or 3.12)
- Git
- (Optional) [Ollama](https://ollama.ai/) for testing local LLM providers
- (Optional) API keys for Anthropic or OpenAI if testing those providers

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/preset-io/testmcpy.git
   cd testmcpy
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install the package in editable mode with development dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

4. (Optional) Install optional features:
   ```bash
   # For web UI development
   pip install -e ".[server]"

   # For Claude SDK integration
   pip install -e ".[sdk]"

   # For all features
   pip install -e ".[all]"
   ```

5. Install pre-commit hooks (recommended):
   ```bash
   pre-commit install
   ```

## Code Quality Standards

### Code Formatting
We use [Black](https://black.readthedocs.io/) for code formatting with a line length of 100 characters.

Run formatting:
```bash
black .
```

### Linting
We use [Flake8](https://flake8.pycqa.org/) for linting.

Run linting:
```bash
flake8 .
```

### Type Checking
We encourage the use of type hints throughout the codebase. Consider using [mypy](http://mypy-lang.org/) for type checking.

## Testing

### Running Tests
```bash
# Run all tests
testmcpy run tests/

# Run specific test file
testmcpy run tests/basic_test.yaml

# Run with specific model
testmcpy run tests/ --model llama3.1:8b --provider ollama

# Run with Claude
testmcpy run tests/ --model claude-haiku-4-5 --provider anthropic
```

### Writing Tests
Test cases are defined in YAML format. See `tests/basic_test.yaml` for examples.

Example test structure:
```yaml
version: "1.0"
name: "Example Test Suite"

tests:
  - name: "test_example"
    prompt: "Your test prompt here"
    expected_tools:
      - "tool_name"
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "tool_name"
      - name: "execution_successful"
```

### Adding New Evaluators
Evaluators should be added to `evals/base_evaluators.py`. Each evaluator should:
- Take a test result and configuration as input
- Return a boolean indicating pass/fail
- Include clear documentation of its purpose
- Handle edge cases gracefully

## Contributing Guidelines

### Pull Request Process
1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes
4. Run tests and ensure they pass
5. Run code formatting and linting
6. Commit your changes with clear, descriptive messages
7. Push to your fork
8. Create a pull request

### Commit Message Guidelines
- Use the imperative mood ("Add feature" not "Added feature")
- Keep the first line under 50 characters
- Include a detailed description if necessary
- Reference issues and pull requests when applicable

Example:
```
Add support for custom evaluator plugins

This commit introduces a plugin system for custom evaluators,
allowing users to extend the framework with domain-specific
validation logic.

Fixes #123
```

### Code Review Process
- All contributions require code review
- Address feedback promptly and respectfully
- Be open to suggestions and improvements
- Ensure your code follows the project's style and conventions

## Important Principles

### Multi-Provider Support
This framework supports both free/local and paid API providers:
- **Always maintain support for free/local options** (Ollama, local models)
- Test changes with multiple providers when possible (Anthropic, OpenAI, Ollama)
- Document provider-specific requirements clearly
- Ensure core functionality works without paid APIs

### Design Philosophy
- **Modularity**: Keep components loosely coupled and highly cohesive
- **Testability**: Write code that can be easily tested
- **Documentation**: Document public APIs and complex logic
- **Performance**: Consider performance implications, especially for test execution
- **Usability**: Prioritize user experience in CLI design

## Areas for Contribution

### High Priority
- Additional evaluators for common testing scenarios
- Support for more LLM providers (prioritize open-source/local options)
- Performance optimizations
- Documentation improvements
- Example integrations with different MCP services

### Medium Priority
- Enhanced reporting capabilities
- Parallel test execution
- CLI usability improvements
- Test case templates for different domains
- Better error messages and debugging tools

### Lower Priority
- Advanced configuration options
- Integration with CI/CD systems (GitHub Actions, etc.)
- Cost tracking and optimization features

## Getting Help

- **Documentation**: Start with [README.md](README.md)
- **Issues**: Check existing [issues](https://github.com/preset-io/testmcpy/issues)
- **Discussions**: Ask questions in [GitHub Discussions](https://github.com/preset-io/testmcpy/discussions)
- **Bug Reports**: Create a new issue with reproduction steps
- **Feature Requests**: Open an issue to discuss before implementing

## Testing Your Changes

Before submitting a pull request:

1. **Run existing tests**: `testmcpy run tests/`
2. **Test with multiple providers** (if applicable): Ollama, Anthropic, OpenAI
3. **Run code formatting**: `black .`
4. **Run linting**: `flake8 .`
5. **Test the CLI** with various commands
6. **Check for sensitive data**: Ensure no API keys or credentials are committed

## Reporting Security Issues

If you discover a security vulnerability, please report it via [GitHub Security Advisories](https://github.com/preset-io/testmcpy/security/advisories/new) instead of opening a public issue.

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.

## Recognition

All contributors are recognized in our release notes. Significant contributions may be highlighted in the README.

## Questions?

Don't hesitate to ask! Open a discussion or comment on an existing issue. We're here to help.

Thank you for contributing to testmcpy!