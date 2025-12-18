# Contributing to testmcpy

Thank you for your interest in contributing to testmcpy! We're excited to have you join our community of contributors building better tools for testing LLM tool-calling capabilities.

We welcome all types of contributions:
- Bug reports and fixes
- New features and evaluators
- Documentation improvements
- Example test cases
- Performance optimizations
- Community support

This guide will help you get started, whether you're fixing a typo or adding a major feature.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Quick Start](#quick-start)
- [Development Setup](#development-setup)
- [Contribution Workflow](#contribution-workflow)
- [Commit Message Format](#commit-message-format)
- [Pull Request Guidelines](#pull-request-guidelines)
- [Code Review Process](#code-review-process)
- [Testing Requirements](#testing-requirements)
- [Code Quality Standards](#code-quality-standards)
- [Community Guidelines](#community-guidelines)
- [Getting Help](#getting-help)

## Code of Conduct

Be respectful, inclusive, and collaborative. We're all here to build better tools for the community.

Key principles:
- **Be respectful**: Treat everyone with respect and kindness
- **Be inclusive**: Welcome contributors of all backgrounds and experience levels
- **Be collaborative**: Share knowledge, help others, and work together
- **Be constructive**: Provide helpful feedback and accept it gracefully
- **Be patient**: Remember that everyone started as a beginner

## Quick Start

Want to contribute quickly? Here's the fastest path:

```bash
# 1. Fork the repository on GitHub
# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/testmcpy.git
cd testmcpy

# 3. Set up development environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev,all]"

# 4. Create a branch for your work
git checkout -b feat/my-new-feature

# 5. Make your changes, test them
testmcpy run tests/

# 6. Format and lint your code
black .
flake8 .

# 7. Commit and push
git add .
git commit -m "feat: add amazing new feature"
git push origin feat/my-new-feature

# 8. Open a pull request on GitHub
```

That's it! Now let's dive into the details.

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

## Contribution Workflow

We follow a standard fork-and-pull workflow. Here's the detailed process:

### 1. Fork and Clone

Fork the repository on GitHub, then clone your fork:

```bash
git clone https://github.com/YOUR_USERNAME/testmcpy.git
cd testmcpy
```

Add the upstream repository as a remote:

```bash
git remote add upstream https://github.com/preset-io/testmcpy.git
```

### 2. Create a Branch

Always create a new branch for your work. Use descriptive branch names with prefixes:

- `feat/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `refactor/` - Code refactoring
- `test/` - Adding or updating tests
- `chore/` - Maintenance tasks

```bash
# Example branch names
git checkout -b feat/parameter-validation-evaluator
git checkout -b fix/chat-command-error
git checkout -b docs/update-readme-examples
```

### 3. Make Changes

Write your code following our standards (see Code Quality Standards below). Make sure to:

- Add type hints for new functions
- Update documentation for user-facing changes
- Add tests for new functionality
- Keep changes focused on a single concern

### 4. Test Your Changes

Before committing, ensure everything works:

```bash
# Run the test suite
testmcpy run tests/

# Test with multiple providers if applicable
testmcpy run tests/ --provider ollama --model llama3.1:8b
testmcpy run tests/ --provider anthropic --model claude-haiku-4-5

# Format and lint
black .
flake8 .

# Type check (if you have mypy installed)
mypy testmcpy
```

### 5. Commit Your Changes

Write clear, descriptive commit messages following our format (see Commit Message Format below):

```bash
git add .
git commit -m "feat: add deep parameter validation evaluators"
```

### 6. Keep Your Branch Updated

Regularly sync with the upstream repository:

```bash
git fetch upstream
git rebase upstream/main
```

### 7. Push to Your Fork

```bash
git push origin feat/your-feature-name
```

### 8. Open a Pull Request

Go to GitHub and open a pull request from your fork to the main repository. Fill out the PR template with:

- Clear description of changes
- Why the change is needed
- How you tested it
- Screenshots (for UI changes)
- Related issue numbers

### 9. Address Review Feedback

Be responsive to feedback from reviewers. Make requested changes and push updates:

```bash
# Make changes based on feedback
git add .
git commit -m "fix: address review feedback"
git push origin feat/your-feature-name
```

## Commit Message Format

We use conventional commits to keep our history clean and enable automated changelog generation.

### Format

```
<type>: <short description>

<optional longer description>

<optional footer>
```

### Types

- `feat`: New feature for users
- `fix`: Bug fix for users
- `docs`: Documentation changes
- `refactor`: Code refactoring (no functional changes)
- `test`: Adding or updating tests
- `chore`: Maintenance tasks, dependency updates
- `perf`: Performance improvements
- `style`: Code style changes (formatting, etc.)

### Examples

**Simple feature:**
```
feat: add parameter_value_in_range evaluator
```

**Bug fix with description:**
```
fix: resolve chat command hanging on empty response

The chat command would hang indefinitely when receiving an empty
response from the LLM. This fix adds proper timeout handling and
error messages for this scenario.

Fixes #42
```

**Feature with breaking change:**
```
feat: change evaluator return format to include metadata

BREAKING CHANGE: Evaluators now return a dict with 'passed', 'score',
and 'reason' keys instead of just a boolean. Update custom evaluators
to use the new format.
```

**Documentation update:**
```
docs: add examples for custom evaluator development
```

**Multiple changes:**
```
feat: add deep parameter validation evaluators

Implements 4 new evaluators for checking tool call parameters:
- tool_called_with_parameter
- tool_called_with_parameters
- parameter_value_in_range
- tool_call_count

Includes comprehensive tests and documentation examples.

Closes #123
```

### Guidelines

- Use the imperative mood ("add" not "added" or "adds")
- Keep the first line under 72 characters
- Don't capitalize the first letter after the type
- Don't end the first line with a period
- Leave a blank line before the body
- Wrap the body at 72 characters
- Reference issues and PRs when applicable

## Pull Request Guidelines

### Before Opening a PR

- [ ] Code follows project style guide (Black formatting, type hints)
- [ ] All tests pass (`testmcpy run tests/`)
- [ ] Code is properly formatted (`black .`)
- [ ] No linting errors (`flake8 .`)
- [ ] New tests added for new functionality
- [ ] Documentation updated if needed
- [ ] Commit messages follow our format
- [ ] Branch is up to date with main

### PR Template Checklist

When you open a PR, fill out the template completely:

**Summary**: Briefly explain what this PR does in 1-2 sentences.

**Changes**: List the main changes made:
- Added X evaluator
- Fixed Y bug in chat command
- Updated Z documentation

**Testing**: Describe how you tested:
- Manual testing with Ollama and Claude
- Added unit tests in `tests/unit/test_evaluators.py`
- Verified existing tests still pass

**Related Issues**: Link any related issues:
- Fixes #123
- Related to #456

### PR Best Practices

1. **Keep PRs focused**: One PR should address one issue or add one feature
2. **Small is better**: Smaller PRs are easier to review and merge
3. **Write good descriptions**: Help reviewers understand your changes
4. **Add screenshots**: For UI changes, include before/after screenshots
5. **Update documentation**: Keep docs in sync with code changes
6. **Respond promptly**: Address review feedback in a timely manner
7. **Don't force push**: After review starts, add new commits instead of rebasing

### What Makes a Good PR?

**Good PR example:**
```markdown
## Summary
Add support for validating tool call parameters to ensure LLMs pass
correct values to MCP tools.

## Changes
- Added `parameter_value_in_range` evaluator
- Added `tool_called_with_parameter` evaluator
- Added tests in `tests/unit/test_param_evaluators.py`
- Updated evaluator reference documentation

## Testing
- Tested with Ollama (llama3.1:8b) and Claude (claude-haiku-4-5)
- All existing tests pass
- New tests cover edge cases (missing params, wrong types, etc.)

## Related Issues
Fixes #42
```

## Code Review Process

### What to Expect

- **Initial response**: We aim to respond to PRs within 2-3 business days
- **Review time**: Most PRs are reviewed within a week
- **Iterations**: Expect 1-2 rounds of feedback for most PRs
- **Approval**: At least one maintainer approval required before merge
- **CI checks**: All CI checks must pass before merge

### Review Criteria

Reviewers will check:

1. **Functionality**: Does it work as intended?
2. **Tests**: Are there adequate tests?
3. **Code quality**: Is the code clean and maintainable?
4. **Documentation**: Are changes documented?
5. **Breaking changes**: Are they necessary and well-communicated?
6. **Performance**: Any performance implications?
7. **Security**: Any security concerns?
8. **Multi-provider support**: Works with all LLM providers?

### How to Get Your PR Merged Faster

1. **Write clear descriptions**: Help reviewers understand context
2. **Add tests**: PRs with tests are easier to approve
3. **Keep it small**: Smaller PRs get reviewed faster
4. **Follow guidelines**: Adhering to our standards speeds up review
5. **Be responsive**: Quick responses to feedback help maintain momentum
6. **Self-review**: Review your own PR before submitting

### After Approval

Once approved:
- Maintainers will merge your PR (usually via squash merge)
- Your contribution will be included in the next release
- You'll be credited in release notes

## Testing Requirements

All code changes should include appropriate tests. Good tests make code more maintainable and give confidence that changes work correctly.

### Types of Tests

1. **Unit Tests**: Test individual functions and evaluators
2. **Integration Tests**: Test YAML test file execution
3. **Provider Tests**: Test with different LLM providers (optional but recommended)

### Test Structure

```python
# tests/unit/test_evaluators.py
import pytest
from testmcpy.evaluators import WasMcpToolCalled

def test_was_mcp_tool_called_success():
    """Test that evaluator passes when correct tool is called."""
    evaluator = WasMcpToolCalled(tool_name="create_chart")
    result = {
        "tool_calls": [{"name": "create_chart", "args": {}}]
    }
    evaluation = evaluator.evaluate(result)

    assert evaluation["passed"] is True
    assert "create_chart" in evaluation["reason"]

def test_was_mcp_tool_called_failure():
    """Test that evaluator fails when wrong tool is called."""
    evaluator = WasMcpToolCalled(tool_name="create_chart")
    result = {
        "tool_calls": [{"name": "delete_chart", "args": {}}]
    }
    evaluation = evaluator.evaluate(result)

    assert evaluation["passed"] is False
```

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

### Writing Test Cases

Test cases are defined in YAML format:

```yaml
version: "1.0"
name: "Example Test Suite"

tests:
  - name: "test_tool_calling"
    prompt: "Create a bar chart showing sales by region"
    expected_tools:
      - "create_chart"
    evaluators:
      - name: "was_mcp_tool_called"
        args:
          tool_name: "create_chart"
      - name: "execution_successful"
      - name: "within_time_limit"
        args:
          max_seconds: 30
```

### Test Coverage Guidelines

When adding new features:

- **Evaluators**: Add unit tests with pass and fail cases
- **CLI commands**: Add integration tests with YAML test files
- **Bug fixes**: Add tests that reproduce the bug
- **Edge cases**: Test error handling and boundary conditions

## Code Quality Standards

We maintain high code quality standards to ensure the codebase is maintainable and reliable.

### Code Formatting

We use [Black](https://black.readthedocs.io/) for code formatting with a line length of 100 characters.

```bash
# Format all code
black .

# Check formatting without making changes
black --check .
```

Black is opinionated and eliminates debates about code style. If Black formats it, it's correct.

### Linting

We use [Flake8](https://flake8.pycqa.org/) for catching common issues.

```bash
# Run linting
flake8 .

# Run with specific config
flake8 testmcpy --max-line-length=100
```

### Type Checking

We encourage comprehensive type hints. Use [mypy](http://mypy-lang.org/) for type checking:

```bash
# Type check the codebase
mypy testmcpy

# Check a specific file
mypy testmcpy/cli.py
```

Example with good type hints:

```python
from typing import Dict, List, Optional

async def evaluate_test(
    test_case: Dict[str, Any],
    result: Dict[str, Any],
    evaluators: List[str]
) -> Dict[str, bool]:
    """Evaluate test results using specified evaluators.

    Args:
        test_case: Test case configuration
        result: Execution result from LLM
        evaluators: List of evaluator names to run

    Returns:
        Dictionary mapping evaluator names to pass/fail results
    """
    # Implementation
    pass
```

### Code Style Guidelines

1. **Use descriptive names**: `get_tool_calls()` not `get_tc()`
2. **Keep functions small**: One function, one purpose
3. **Document complex logic**: Add comments for non-obvious code
4. **Use type hints**: Help others understand your code
5. **Handle errors gracefully**: Don't let exceptions crash the CLI
6. **Use async/await**: For I/O operations with LLMs and APIs

### Documentation Standards

- **Docstrings**: Use Google-style docstrings for all public functions
- **Comments**: Explain why, not what (code shows what)
- **Type hints**: Required for all public functions
- **Examples**: Add examples in docstrings for complex functions

Example:

```python
def evaluate_parameter_range(
    parameter_name: str,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None
) -> bool:
    """Check if a parameter value is within the specified range.

    Args:
        parameter_name: Name of the parameter to check
        min_value: Minimum allowed value (inclusive), None for no minimum
        max_value: Maximum allowed value (inclusive), None for no maximum

    Returns:
        True if value is in range, False otherwise

    Examples:
        >>> evaluate_parameter_range("temperature", min_value=0, max_value=1)
        True
        >>> evaluate_parameter_range("count", min_value=1)
        True
    """
    # Implementation
    pass
```

## Community Guidelines

Building a welcoming, inclusive community is core to testmcpy's success.

### Our Values

- **Welcoming**: We welcome contributors of all skill levels and backgrounds
- **Respectful**: Treat everyone with respect and professionalism
- **Collaborative**: Share knowledge, help others learn, and work together
- **Inclusive**: Use inclusive language and consider diverse perspectives
- **Constructive**: Give helpful feedback and receive it graciously
- **Open**: Be transparent about decisions and open to new ideas

### Multi-Provider Philosophy

This framework supports both free/local and paid API providers:

- **Always maintain support for free/local options** (Ollama, local models)
- Test changes with multiple providers when possible (Anthropic, OpenAI, Ollama)
- Document provider-specific requirements clearly
- Ensure core functionality works without paid APIs
- Make paid features optional, not required

This ensures testmcpy remains accessible to everyone, regardless of budget.

### Design Philosophy

- **Modularity**: Keep components loosely coupled and highly cohesive
- **Testability**: Write code that can be easily tested
- **Documentation**: Document public APIs and complex logic
- **Performance**: Consider performance implications, especially for test execution
- **Usability**: Prioritize user experience in CLI design
- **Extensibility**: Make it easy for users to add custom evaluators and integrations

### Communication

- **Issues**: Use GitHub Issues for bug reports and feature requests
- **Discussions**: Use GitHub Discussions for questions and community chat
- **Pull Requests**: Use PRs for code contributions with clear descriptions
- **Be patient**: Maintainers are often volunteers with limited time
- **Be specific**: Provide details, examples, and context in issues and PRs

## Areas for Contribution

We welcome contributions in many areas. Here are some ideas to get started:

### High Priority

- **Evaluators**: Add new evaluators for common testing scenarios
- **Provider support**: Add support for more LLM providers (prioritize open-source/local)
- **Documentation**: Improve guides, add examples, fix typos
- **Examples**: Add example test suites for different MCP services
- **Bug fixes**: Fix reported issues and improve error handling

### Medium Priority

- **Reporting**: Enhanced reporting and visualization of test results
- **Performance**: Optimize test execution and parallel processing
- **CLI UX**: Improve command-line usability and help text
- **Templates**: Create test case templates for different domains
- **Error messages**: Better error messages and debugging tools

### Good First Issues

Looking for a way to get started? Look for issues labeled `good-first-issue`:

- Documentation improvements
- Adding new evaluators with examples
- Writing test cases
- Fixing simple bugs
- Improving error messages

### Lower Priority

- Advanced configuration options
- Integration with CI/CD platforms
- Cost tracking and optimization features
- Performance benchmarking tools

## Getting Help

We're here to help you contribute successfully!

### Resources

- **Documentation**: Start with [README.md](README.md)
- **API Reference**: Check [docs/EVALUATOR_REFERENCE.md](docs/EVALUATOR_REFERENCE.md)
- **Client Guide**: See [docs/CLIENT_USAGE_GUIDE.md](docs/CLIENT_USAGE_GUIDE.md)
- **Examples**: Browse the `tests/` directory for examples

### Ask Questions

- **GitHub Discussions**: Best place for general questions and discussions
- **Issue Comments**: Ask questions on specific issues
- **Pull Request Reviews**: Clarify feedback in PR comments

### Report Issues

When reporting bugs:

1. **Search first**: Check if the issue already exists
2. **Provide details**: Include steps to reproduce, expected vs actual behavior
3. **Include context**: OS, Python version, testmcpy version
4. **Share config**: Include relevant configuration (remove API keys!)
5. **Show errors**: Include full error messages and stack traces

### Request Features

When requesting features:

1. **Describe the problem**: What are you trying to accomplish?
2. **Propose a solution**: How might this feature work?
3. **Consider alternatives**: What other approaches have you considered?
4. **Gauge interest**: Would others benefit from this feature?

## Pre-Submit Checklist

Before submitting your pull request, ensure:

- [ ] Code follows project style guide (Black formatting, type hints)
- [ ] All tests pass (`testmcpy run tests/`)
- [ ] Code is properly formatted (`black .`)
- [ ] No linting errors (`flake8 .`)
- [ ] New tests added for new functionality
- [ ] Documentation updated if needed
- [ ] Commit messages follow conventional commits format
- [ ] Branch is up to date with main
- [ ] No API keys or credentials in code
- [ ] PR description is clear and complete

## Security

### Reporting Security Issues

If you discover a security vulnerability, please report it via [GitHub Security Advisories](https://github.com/preset-io/testmcpy/security/advisories/new) instead of opening a public issue.

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

We'll respond promptly and work with you to address the issue.

### Security Best Practices

When contributing:

- Never commit API keys, tokens, or credentials
- Use `.env` files for local secrets (already in `.gitignore`)
- Validate user input in CLI commands
- Handle errors without exposing sensitive information
- Use HTTPS for all API calls

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.

This means:
- Your code will be open source
- Anyone can use, modify, and distribute it
- You retain copyright to your contributions
- You grant others permission to use your code

## Recognition

We value and recognize all contributors!

- **Contributors list**: All contributors are listed in release notes
- **Significant contributions**: Major features may be highlighted in README
- **First-time contributors**: We celebrate your first contribution
- **Documentation**: Non-code contributions are equally valued

Your contributions make testmcpy better for everyone. Thank you!

## Additional Resources

### Learning Resources

- **MCP Documentation**: [Model Context Protocol](https://modelcontextprotocol.io/)
- **Anthropic API**: [Anthropic Docs](https://docs.anthropic.com/)
- **Python Async**: [Async/Await Guide](https://realpython.com/async-io-python/)
- **Type Hints**: [Python Type Hints](https://docs.python.org/3/library/typing.html)

### Related Projects

- **fastmcp**: Fast MCP server implementation
- **claude-agent-sdk**: Claude agent SDK
- **MCP servers**: Various MCP server implementations

## Questions?

Still have questions? Don't hesitate to ask!

- Open a [GitHub Discussion](https://github.com/preset-io/testmcpy/discussions)
- Comment on an existing issue
- Reach out in your pull request

We're here to help you succeed. Welcome to the testmcpy community!

---

Thank you for contributing to testmcpy!