# Development Guide

Guide for setting up testmcpy for development and contributing to the project.

## Development Setup

### Prerequisites

- Python 3.9 - 3.12
- Git
- Node.js 18+ (for UI development)
- Virtual environment tool

### Clone Repository

```bash
git clone https://github.com/preset-io/testmcpy.git
cd testmcpy
```

### Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip

# Install in editable mode with all dev dependencies
pip install -e '.[dev]'
```

### Install Development Dependencies

The `[dev]` extra includes:

- **pytest** - Testing framework
- **black** - Code formatter
- **mypy** - Type checker
- **ruff** - Fast Python linter
- **pre-commit** - Git hooks for code quality

### Set Up Pre-commit Hooks (Recommended)

```bash
# Install pre-commit hooks
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

This automatically runs linting and formatting before each commit.

## Project Structure

```
testmcpy/
├── testmcpy/                 # Main package
│   ├── __init__.py
│   ├── cli.py               # CLI interface (Click)
│   ├── config.py            # Configuration management
│   ├── mcp_profiles.py      # Profile-based configuration
│   ├── src/                 # Core modules
│   │   ├── mcp_client.py    # MCP protocol client
│   │   ├── llm_integration.py  # LLM provider abstraction
│   │   ├── test_runner.py   # Test execution engine
│   │   └── utils.py         # Utility functions
│   ├── evals/               # Evaluator implementations
│   │   ├── base_evaluators.py
│   │   ├── superset_evaluators.py
│   │   └── __init__.py
│   ├── server/              # Web UI backend (FastAPI)
│   │   ├── api.py
│   │   ├── websocket.py
│   │   └── __init__.py
│   └── ui/                  # React web UI
│       ├── src/
│       ├── public/
│       ├── package.json
│       └── vite.config.ts
├── tests/                   # Test files
│   ├── unit/
│   ├── integration/
│   └── test_*.yaml
├── docs/                    # Documentation
├── examples/                # Example test files
├── .github/                 # GitHub Actions workflows
├── pyproject.toml           # Python project metadata
├── setup.py                 # Package setup
└── README.md
```

## Running Tests

### Python Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=testmcpy --cov-report=html

# Run specific test file
pytest tests/unit/test_evaluators.py

# Run with verbose output
pytest -v

# Run tests matching pattern
pytest -k "test_mcp"
```

### Test Organization

- `tests/unit/` - Unit tests for individual components
- `tests/integration/` - Integration tests with MCP services
- `tests/*.yaml` - Example test definitions

### Writing Tests

```python
# tests/unit/test_evaluators.py
import pytest
from testmcpy.evals.base_evaluators import ExecutionSuccessful

def test_execution_successful_pass():
    """Test ExecutionSuccessful evaluator with passing result."""
    evaluator = ExecutionSuccessful()
    context = {
        "tool_results": [{"is_error": False}],
        "metadata": {}
    }
    result = evaluator.evaluate(context)
    assert result.passed
    assert result.score == 1.0

def test_execution_successful_fail():
    """Test ExecutionSuccessful evaluator with error."""
    evaluator = ExecutionSuccessful()
    context = {
        "tool_results": [{"is_error": True, "error_message": "Test error"}],
        "metadata": {}
    }
    result = evaluator.evaluate(context)
    assert not result.passed
    assert result.score == 0.0
```

## Code Quality

### Formatting with Black

```bash
# Format all files
black .

# Check formatting without changes
black --check .

# Format specific file
black testmcpy/cli.py
```

Black configuration in `pyproject.toml`:

```toml
[tool.black]
line-length = 100
target-version = ['py39', 'py310', 'py311', 'py312']
```

### Linting with Ruff

```bash
# Run linter
ruff check .

# Auto-fix issues
ruff check --fix .

# Check specific file
ruff check testmcpy/cli.py
```

### Type Checking with mypy

```bash
# Check all files
mypy testmcpy

# Check specific file
mypy testmcpy/cli.py

# Ignore missing imports
mypy --ignore-missing-imports testmcpy
```

## UI Development

### Set Up UI Development Environment

```bash
cd testmcpy/ui

# Install dependencies
npm install

# Start development server
npm run dev
```

The UI will be available at http://localhost:5173

### UI Development Commands

```bash
# Development server with hot reload
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Lint TypeScript/React code
npm run lint

# Format code
npm run format
```

### UI Project Structure

```
testmcpy/ui/
├── src/
│   ├── components/      # React components
│   ├── pages/          # Page components
│   ├── hooks/          # Custom React hooks
│   ├── api/            # API client
│   ├── types/          # TypeScript types
│   └── App.tsx         # Main app component
├── public/             # Static assets
├── package.json
├── vite.config.ts      # Vite configuration
└── tsconfig.json       # TypeScript configuration
```

## Working with the CLI

### Testing CLI Commands

```bash
# Install in editable mode
pip install -e .

# Test commands
testmcpy --help
testmcpy tools
testmcpy run tests/

# Test with different configs
testmcpy --config=.env.dev run tests/
```

### Adding New CLI Commands

Edit `testmcpy/cli.py`:

```python
import click

@click.command()
@click.option('--param', help='Parameter description')
def my_new_command(param):
    """Description of what this command does."""
    click.echo(f"Running command with param: {param}")

# Add to CLI group
cli.add_command(my_new_command)
```

## Working with Evaluators

### Creating New Evaluators

1. Create evaluator class in `testmcpy/evals/base_evaluators.py`:

```python
from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class EvalResult:
    passed: bool
    score: float
    reason: str
    details: Dict[str, Any] = None

class BaseEvaluator:
    """Base class for all evaluators."""

    @property
    def name(self) -> str:
        raise NotImplementedError

    @property
    def description(self) -> str:
        raise NotImplementedError

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        raise NotImplementedError

class MyNewEvaluator(BaseEvaluator):
    """Evaluator description."""

    def __init__(self, param1: str, param2: int = 10):
        self.param1 = param1
        self.param2 = param2

    @property
    def name(self) -> str:
        return "my_new_evaluator"

    @property
    def description(self) -> str:
        return f"Checks {self.param1} against {self.param2}"

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        # Access context
        prompt = context.get("prompt")
        response = context.get("response")
        tool_calls = context.get("tool_calls", [])
        tool_results = context.get("tool_results", [])
        metadata = context.get("metadata", {})

        # Your evaluation logic
        passed = True  # Your condition
        score = 1.0 if passed else 0.0

        return EvalResult(
            passed=passed,
            score=score,
            reason="Reason for result",
            details={"key": "value"}
        )
```

2. Register in factory function:

```python
def create_evaluator(name: str, **kwargs) -> BaseEvaluator:
    evaluators = {
        # ... existing evaluators
        "my_new_evaluator": MyNewEvaluator,
    }
    return evaluators[name](**kwargs)
```

3. Add tests:

```python
# tests/unit/test_my_evaluator.py
def test_my_new_evaluator():
    evaluator = MyNewEvaluator(param1="test", param2=5)
    context = {
        "prompt": "test prompt",
        "response": "test response",
        "tool_calls": [],
        "tool_results": [],
        "metadata": {}
    }
    result = evaluator.evaluate(context)
    assert result.passed
```

4. Document in `docs/api/evaluators.md`

## Debugging

### Using Python Debugger

```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use built-in breakpoint()
breakpoint()
```

### Debug with VS Code

`.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: testmcpy",
      "type": "python",
      "request": "launch",
      "module": "testmcpy.cli",
      "args": ["run", "tests/my_test.yaml", "--verbose"],
      "console": "integratedTerminal"
    }
  ]
}
```

### Verbose Logging

```bash
# Enable verbose output
testmcpy run tests/ --verbose

# Set log level via environment
export LOG_LEVEL=DEBUG
testmcpy run tests/
```

## Contributing

### Contribution Workflow

1. **Fork the repository** on GitHub
2. **Clone your fork** locally
3. **Create a branch** for your feature
4. **Make your changes** with tests
5. **Run tests and linting**
6. **Commit your changes** with conventional commits
7. **Push to your fork**
8. **Open a pull request**

### Branch Naming

```bash
# Feature branches
git checkout -b feat/add-new-evaluator

# Bug fixes
git checkout -b fix/parameter-validation

# Documentation
git checkout -b docs/update-quickstart
```

### Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <description>

<optional body>

<optional footer>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:

```bash
git commit -m "feat: add parameter range validation evaluator"
git commit -m "fix: handle null values in tool results"
git commit -m "docs: update installation guide with Python 3.12"
```

### Pull Request Checklist

Before opening a PR:

- [ ] Tests pass (`pytest`)
- [ ] Code is formatted (`black .`)
- [ ] Linting passes (`ruff check .`)
- [ ] Type checking passes (`mypy testmcpy`)
- [ ] Documentation updated (if needed)
- [ ] CHANGELOG.md updated (if user-facing change)
- [ ] Commit messages follow conventional format

### Code Review Process

1. PR is automatically checked by CI
2. Maintainer reviews code
3. Address feedback with new commits
4. Once approved, maintainer merges PR
5. Your contribution is recognized in README

## Release Process

### Version Bumping

```bash
# Update version in setup.py and __init__.py
# Follow semantic versioning (MAJOR.MINOR.PATCH)

# Commit version bump
git commit -m "chore: bump version to 0.3.0"

# Tag release
git tag v0.3.0
git push origin v0.3.0
```

### Building Package

```bash
# Install build tools
pip install build twine

# Build UI
cd testmcpy/ui
npm install
npm run build
cd ../..

# Build package
python -m build

# Check built package
twine check dist/*
```

### Publishing to PyPI

```bash
# Test on TestPyPI first
twine upload --repository testpypi dist/*

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ testmcpy

# If all good, publish to PyPI
twine upload dist/*
```

## Documentation

### Building Documentation

Documentation uses Markdown files in `docs/`.

### Adding Documentation

1. Create or edit `.md` files in `docs/`
2. Update `docs/index.md` with links
3. Follow existing structure and style
4. Include code examples
5. Test all commands and code snippets

### Documentation Structure

- `guide/` - User guides and tutorials
- `api/` - API and reference documentation
- `examples/` - Example use cases
- `index.md` - Documentation home page

## Getting Help

- **GitHub Issues**: Report bugs or request features
- **GitHub Discussions**: Ask questions, share ideas
- **Code of Conduct**: Be respectful and constructive

## Useful Resources

- [Click Documentation](https://click.palletsprojects.com/) - CLI framework
- [FastAPI Documentation](https://fastapi.tiangolo.com/) - Web framework
- [pytest Documentation](https://docs.pytest.org/) - Testing framework
- [Black Documentation](https://black.readthedocs.io/) - Code formatter
- [Ruff Documentation](https://docs.astral.sh/ruff/) - Linter
