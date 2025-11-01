# Open Source Best Practices (Learned from Agor)

This document outlines best practices for open-sourcing testmcpy, inspired by the [agor repository](https://github.com/mistercrunch/agor).

## Executive Summary

Agor is a well-structured open source project by Maxime Beauchemin (Apache Superset/Airflow creator) that demonstrates excellent practices for:
- Documentation structure
- Contribution workflows
- Development tooling
- Code organization
- Community engagement

We should adopt these patterns for testmcpy.

---

## 1. Documentation Structure

### What Agor Does Well

#### README.md
- **Visual-first**: Screenshots, GIFs, and diagrams at the top
- **Clear value proposition**: One-sentence elevator pitch
- **Installation in 3 steps**: Dead simple quick start
- **Architecture diagram**: Mermaid diagram showing system components
- **Feature showcase**: Grid of screenshots with captions
- **Links to external docs**: Separate docs site for deep content

#### CONTRIBUTING.md
- **Link to full guide**: Points to comprehensive docs, keeps file focused
- **Quick start section**: Docker one-liner to get started
- **Contribution workflow**: Step-by-step with code examples
- **Commit message format**: Clear examples of good commits
- **PR template guidance**: What to include in PR descriptions
- **Code review expectations**: Timeline and process
- **Community guidelines**: Be respectful, ask questions, collaborate

#### Context Documentation (`context/` directory)
- **Structured knowledge**: Organized into concepts/, guidelines/, projects/
- **Versioned docs**: Archives old versions, keeps current docs fresh
- **For LLMs**: Specifically formatted for Claude/AI consumption
- **Modular**: Each concept in separate file, composable

### What We Should Add

```
testmcpy/
├── README.md (update with visuals, clearer structure)
├── CONTRIBUTING.md (create comprehensive guide)
├── LICENSE (already have Apache 2.0 ✓)
├── .github/
│   ├── PULL_REQUEST_TEMPLATE.md (already have ✓)
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   ├── feature_request.md
│   │   └── question.md
│   └── workflows/ (CI/CD)
├── docs/
│   ├── guide/
│   │   ├── quickstart.md
│   │   ├── installation.md
│   │   ├── development.md
│   │   ├── architecture.md
│   │   └── contributing.md
│   ├── api/
│   │   ├── cli.md
│   │   ├── evaluators.md
│   │   └── test-format.md
│   └── examples/
│       ├── basic-test.md
│       ├── ci-cd-integration.md
│       └── custom-evaluators.md
└── .claude/
    ├── context.md (already have ✓)
    ├── project.json (already have ✓)
    └── project.md (already have ✓)
```

---

## 2. README Improvements

### Current State
- ✅ Has installation instructions
- ✅ Has basic usage examples
- ❌ No screenshots/visuals
- ❌ No clear value proposition at top
- ❌ No architecture diagram
- ❌ No contributor recognition

### Recommended Changes

#### Top Section (Above the fold)
```markdown
# testmcpy

**Test and benchmark LLMs with MCP tools**

A testing framework for validating LLM tool calling behavior with Model Context Protocol (MCP) services.

[Screenshots] [Demo GIF] [Architecture Diagram]

**[Documentation](https://preset-io.github.io/testmcpy)** | **[Examples](./examples)** | **[Contributing](./CONTRIBUTING.md)**

## Quick Start

\`\`\`bash
pip install testmcpy
testmcpy init
testmcpy serve  # Opens UI at http://localhost:8000
\`\`\`
```

#### Add Visual Elements
1. **Screenshot of UI**: Chat interface showing test execution
2. **GIF**: Test runner in action with progress bars
3. **Diagram**: Architecture showing CLI → Server → MCP → LLM flow
4. **Feature showcase**: Grid of 2-4 screenshots showing key features

#### Add Key Sections
- **Why testmcpy?**: 3-4 bullets explaining the problem it solves
- **Features**: Visual list of capabilities
- **Use Cases**: Who should use this and why
- **Examples**: Link to /examples directory
- **Contributors**: Recognize contributors

---

## 3. Development Tooling

### What Agor Uses

#### Code Quality
- **Biome**: Fast linter/formatter (replaces ESLint + Prettier)
- **TypeScript strict mode**: Full type safety
- **Husky**: Git hooks for pre-commit checks
- **lint-staged**: Only lint changed files
- **Turbo**: Monorepo build system
- **pnpm**: Fast, efficient package manager

#### Testing
- **Vitest**: Fast test runner
- **Storybook**: Component development/testing
- **Testing Library**: React component tests

#### CI/CD
- GitHub Actions for automated checks
- Type checking, linting, tests on every PR
- Automated releases

### What We Should Add

#### Python Equivalents

```toml
# pyproject.toml additions

[tool.ruff]
# Fast Python linter/formatter (like Biome)
line-length = 100
target-version = "py39"

[tool.pytest]
# Test configuration
testpaths = ["tests"]
python_files = ["test_*.py"]

[tool.mypy]
# Type checking
python_version = "3.9"
strict = true
warn_return_any = true

[tool.coverage]
# Test coverage
[tool.coverage.run]
source = ["testmcpy"]
omit = ["tests/*", "testmcpy/ui/*"]

[tool.coverage.report]
exclude_lines = ["pragma: no cover", "def __repr__", "raise AssertionError"]
```

#### Pre-commit Hooks

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
```

#### GitHub Actions Workflow

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main, dev]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.9", "3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Lint
        run: ruff check .

      - name: Type check
        run: mypy testmcpy

      - name: Test
        run: pytest --cov=testmcpy --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4

  ui:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20

      - name: Install UI dependencies
        run: cd testmcpy/ui && npm install

      - name: Build UI
        run: cd testmcpy/ui && npm run build

      - name: Test UI
        run: cd testmcpy/ui && npm test
```

---

## 4. Contribution Workflow

### Agor's Process

1. **Fork/Clone**
2. **Create branch** (feat/fix/docs prefix)
3. **Make changes** (with type checking and linting)
4. **Commit** (conventional commit format)
5. **Push** (triggers CI checks)
6. **Open PR** (with template)
7. **Review** (maintainer approval required)
8. **Merge** (squash commit)
9. **Recognition** (added to contributors list)

### Key Points

#### Commit Messages
```
<type>: <short description>

<optional longer description>

<optional footer>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

Examples:
```
feat: add deep parameter validation evaluators

Implements 4 new evaluators for checking tool call parameters:
- tool_called_with_parameter
- tool_called_with_parameters
- parameter_value_in_range
- tool_call_count

Closes #42
```

#### PR Template

Create `.github/PULL_REQUEST_TEMPLATE.md`:

```markdown
## What

Brief description of what this PR does.

## Why

Why is this change needed? What problem does it solve?

## How

Brief explanation of approach (if non-obvious).

## Testing

- [ ] Added tests for new functionality
- [ ] Existing tests pass
- [ ] Manually tested the following scenarios:
  - ...

## Screenshots

(For UI changes, include before/after screenshots)

## Checklist

- [ ] Code follows project style guide
- [ ] Documentation updated (if needed)
- [ ] Tests added/updated (if needed)
- [ ] CHANGELOG.md updated (if user-facing change)

Closes #<issue-number>
```

---

## 5. Code Organization

### Agor's Monorepo Structure

```
agor/
├── apps/
│   ├── agor-cli/        # CLI tool
│   ├── agor-daemon/     # Backend server
│   └── agor-ui/         # React UI
├── packages/
│   ├── core/            # Shared types and utils
│   └── docs/            # Documentation site
├── context/             # LLM knowledge base
│   ├── concepts/
│   ├── guidelines/
│   └── projects/
├── scripts/             # Build/deploy scripts
└── .github/             # GitHub config
```

### Benefits
- Clear separation of concerns
- Shared code in packages/core
- Independent versioning per app
- Documentation as a package

### Testmcpy Structure (Current)

```
testmcpy/
├── testmcpy/
│   ├── cli.py
│   ├── server/
│   ├── src/
│   ├── evals/
│   ├── ui/              # React UI (separate build)
│   └── research/
├── tests/
├── docs/
└── .claude/
```

### Recommended Refactoring

```
testmcpy/
├── src/
│   └── testmcpy/        # Python package
│       ├── cli/         # CLI commands
│       ├── server/      # FastAPI server
│       ├── core/        # Core logic
│       ├── evaluators/  # Evaluator implementations
│       └── ui/          # React UI (built to dist/)
├── tests/               # Python tests
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── docs/                # Documentation
│   ├── guide/
│   ├── api/
│   └── examples/
├── examples/            # Example test files
│   ├── basic/
│   ├── ci-cd/
│   └── custom-evaluators/
├── scripts/             # Dev/build scripts
├── .github/             # GitHub config
│   ├── workflows/
│   └── ISSUE_TEMPLATE/
└── .claude/             # Claude context
```

---

## 6. Community Engagement

### What Agor Does

#### GitHub Features
- **Discussions**: For questions, ideas, and community chat
- **Issues**: Clearly labeled (bug, feature, question, help-wanted, good-first-issue)
- **Roadmap**: Public roadmap in issues with "roadmap" label
- **Releases**: Detailed release notes with contributor credits
- **Wiki**: Additional documentation

#### Communication
- **Response time expectations**: Documented in CONTRIBUTING.md
- **Code of conduct**: Respectful, inclusive language
- **Recognition**: Contributors list in README
- **Transparency**: Public roadmap and decision-making

### What We Should Add

1. **Enable GitHub Discussions**
   - Categories: Q&A, Ideas, Show & Tell, General

2. **Create Issue Labels**
   - `bug` - Something isn't working
   - `feature` - New feature request
   - `documentation` - Improvements to docs
   - `good-first-issue` - Good for newcomers
   - `help-wanted` - Extra attention needed
   - `question` - Further information requested
   - `roadmap` - Future planning
   - `priority:high` - High priority
   - `priority:low` - Low priority

3. **Set up Projects**
   - Roadmap board
   - Bug triage board
   - Feature backlog

4. **Create CHANGELOG.md**
   - Keep a chronological list of changes
   - Link to PRs and issues
   - Recognize contributors

5. **Add CODE_OF_CONDUCT.md**
   - Use Contributor Covenant template
   - Define acceptable behavior
   - Enforcement procedures

---

## 7. Release Process

### Agor's Approach

- Semantic versioning (v0.3.15)
- GitHub releases with detailed notes
- npm publishing for CLI tool
- Docker images for daemon
- Automated via GitHub Actions

### Testmcpy Release Workflow

1. **Version bumping**: Use `bump2version` or `poetry version`
2. **Changelog**: Update CHANGELOG.md with changes
3. **Tag**: Create git tag with version
4. **Build**: Build Python package and UI
5. **Publish**: Upload to PyPI
6. **Release**: Create GitHub release with notes
7. **Announce**: Post in Discussions

#### Automated Release Workflow

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install build tools
        run: pip install build twine

      - name: Build UI
        run: |
          cd testmcpy/ui
          npm install
          npm run build

      - name: Build Python package
        run: python -m build

      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
        run: twine upload dist/*

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: |
            dist/*.whl
            dist/*.tar.gz
```

---

## 8. UI/UX Lessons from Agor

### Design Philosophy

Agor uses **Ant Design** (antd) for UI components, which provides:
- Professional, enterprise-grade components
- Consistent design language
- Accessibility built-in
- Dark mode support
- Comprehensive component library

### Key UI Patterns

#### 1. Ant Design Components
```tsx
import { ConfigProvider, theme } from 'antd';

// Dark theme configuration
<ConfigProvider
  theme={{
    algorithm: theme.darkAlgorithm,
    token: {
      colorPrimary: '#1890ff',
      borderRadius: 6,
    },
  }}
>
  <App />
</ConfigProvider>
```

#### 2. Modal-based Settings
- Settings in modal, not separate page
- Tabbed interface for different sections
- Inline editing with save/cancel

#### 3. Rich Data Tables
- Sortable, filterable columns
- Inline actions (edit, delete)
- Pagination built-in
- Loading states

#### 4. Real-time Updates
- WebSocket for live data
- Optimistic UI updates
- Toast notifications for actions

### What We Could Adopt

1. **Consider Ant Design**: More polished than our current custom design
   - Pro: Professional, feature-rich, well-documented
   - Con: Heavier bundle size, opinionated styling

2. **Modal Patterns**: Use modals for focused tasks instead of page navigation

3. **Better Tables**: Use data table library for tool/test management

4. **Loading States**: More comprehensive loading/error states

---

## 9. Documentation Site

### Agor's Docs

- Hosted at https://agor.live
- Built with VitePress (Vue-based)
- Sections: Guide, API, Blog, Examples
- Search functionality
- Mobile responsive
- Dark mode

### Testmcpy Docs Plan

#### Option 1: MkDocs Material (Python-native)
```yaml
# mkdocs.yml
site_name: testmcpy
theme:
  name: material
  features:
    - navigation.tabs
    - navigation.sections
    - toc.integrate
    - search.suggest
  palette:
    - scheme: slate
      primary: indigo
      accent: indigo

nav:
  - Home: index.md
  - Guide:
    - Quick Start: guide/quickstart.md
    - Installation: guide/installation.md
    - Development: guide/development.md
  - API:
    - CLI: api/cli.md
    - Evaluators: api/evaluators.md
  - Examples:
    - Basic Test: examples/basic.md
    - CI/CD: examples/ci-cd.md
```

#### Option 2: Docusaurus (React-based)
- More feature-rich
- Better for interactive examples
- Supports MDX (JSX in Markdown)

---

## 10. Testing Standards

### What Agor Tests

- Unit tests for core logic
- Integration tests for services
- Component tests for UI (Storybook)
- E2E tests (planned)

### Testmcpy Testing Plan

```python
# tests/unit/test_evaluators.py
import pytest
from testmcpy.evaluators import ExecutionSuccessful

def test_execution_successful_pass():
    """Test ExecutionSuccessful evaluator with passing result."""
    evaluator = ExecutionSuccessful()
    result = {
        "execution_successful": True,
        "error": None
    }
    assert evaluator.evaluate(result) == {
        "passed": True,
        "score": 1.0,
        "reason": "Execution completed successfully"
    }

# tests/integration/test_cli.py
def test_cli_run_command(tmp_path):
    """Test CLI run command with test file."""
    test_file = tmp_path / "test.yaml"
    test_file.write_text("""
    version: "1.0"
    tests:
      - name: test_example
        prompt: "Test prompt"
        evaluators:
          - name: execution_successful
    """)

    result = subprocess.run(
        ["testmcpy", "run", str(test_file)],
        capture_output=True,
        text=True
    )

    assert result.returncode == 0
    assert "1/1 tests passed" in result.stdout

# tests/e2e/test_ui.py (using Playwright)
async def test_ui_test_runner(page):
    """Test UI test runner flow."""
    await page.goto("http://localhost:8000")
    await page.click("text=Tests")
    await page.click("text=test_example.yaml")
    await page.click("text=Run Tests")
    await page.wait_for_selector("text=Test Results")
    await expect(page.locator("text=PASS")).to_be_visible()
```

---

## Implementation Roadmap

### Phase 1: Documentation (Week 1)
- [ ] Update README.md with visuals and clear structure
- [ ] Create CONTRIBUTING.md
- [ ] Add CODE_OF_CONDUCT.md
- [ ] Create issue templates
- [ ] Set up GitHub Discussions
- [ ] Add CHANGELOG.md

### Phase 2: Development Tooling (Week 2)
- [ ] Add pre-commit hooks (.pre-commit-config.yaml)
- [ ] Set up GitHub Actions CI
- [ ] Add test coverage reporting
- [ ] Configure ruff/mypy
- [ ] Add release automation

### Phase 3: Code Quality (Week 3)
- [ ] Reorganize project structure
- [ ] Add comprehensive tests
- [ ] Improve type hints coverage
- [ ] Add docstrings
- [ ] Update examples/

### Phase 4: Community (Week 4)
- [ ] Set up documentation site
- [ ] Create roadmap board
- [ ] Add contributor recognition
- [ ] Write blog post announcing project
- [ ] Submit to Python Weekly, etc.

---

## Key Takeaways

### What Makes Agor Great

1. **Documentation-first**: README is a landing page, not a file
2. **Visual communication**: Screenshots, GIFs, and diagrams everywhere
3. **Low barrier to entry**: 3-step quick start, Docker one-liner
4. **Tooling investment**: Biome, Turbo, Husky make development smooth
5. **Community focus**: Discussions, recognition, transparent roadmap
6. **Professional polish**: Everything feels well-thought-out

### What We Should Prioritize

1. **README overhaul** - Make it visual and compelling
2. **CONTRIBUTING.md** - Clear process encourages contributions
3. **CI/CD** - Automated testing builds confidence
4. **Documentation site** - Central hub for all docs
5. **Community features** - Discussions, roadmap, recognition

### What We Can Skip (For Now)

1. Monorepo structure - Not needed yet, single package is fine
2. Complex release process - Manual releases OK until automated
3. Storybook - Nice-to-have but not critical
4. Extensive E2E tests - Start with unit/integration

---

## Resources

- **Agor Repository**: https://github.com/mistercrunch/agor
- **Agor Docs**: https://agor.live
- **Ant Design**: https://ant.design
- **MkDocs Material**: https://squidfunk.github.io/mkdocs-material/
- **pre-commit**: https://pre-commit.com
- **Ruff**: https://docs.astral.sh/ruff/
- **GitHub Actions**: https://docs.github.com/en/actions

---

## Next Steps

1. **Review this document** with team
2. **Prioritize improvements** based on impact/effort
3. **Create issues** for each improvement
4. **Start with Phase 1** (documentation)
5. **Iterate and improve** based on feedback

Remember: **Perfect is the enemy of good.** Start with high-impact, low-effort improvements and iterate from there.
