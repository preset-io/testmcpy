# CI/CD Integration Examples

This directory contains example CI/CD configuration files for integrating testmcpy into your continuous integration pipeline.

## Available Examples

### GitHub Actions
- **File**: `github-actions.yml`
- **Copy to**: `.github/workflows/mcp-tests.yml`
- **Features**:
  - Matrix testing across multiple LLM models
  - Service health checks
  - Automatic test result uploads
  - PR comment with results
  - Model comparison reports

### GitLab CI/CD
- **File**: `gitlab-ci.yml`
- **Copy to**: `.gitlab-ci.yml` in your repository root
- **Features**:
  - Multi-stage pipeline
  - Docker service integration
  - Scheduled tests
  - Manual full test suite trigger
  - Comparison reports

## Quick Setup

### 1. Choose Your Platform

Pick the appropriate file for your CI/CD platform and copy it to your repository:

```bash
# GitHub Actions
cp examples/ci-cd/github-actions.yml .github/workflows/mcp-tests.yml

# GitLab CI
cp examples/ci-cd/gitlab-ci.yml .gitlab-ci.yml
```

### 2. Configure Secrets

#### GitHub Actions Secrets

Go to your repository → Settings → Secrets and variables → Actions → New repository secret

Add these secrets:
- `ANTHROPIC_API_KEY` - Your Anthropic API key
- `OPENAI_API_KEY` - Your OpenAI API key (if using GPT models)
- `MCP_AUTH_TOKEN` - Bearer token for your MCP service
- `TEST_DATABASE_URL` - Database connection string (if needed)

#### GitLab CI/CD Variables

Go to your repository → Settings → CI/CD → Variables → Add variable

Add these variables (mark as "Protected" and "Masked"):
- `ANTHROPIC_API_KEY` - Your Anthropic API key
- `OPENAI_API_KEY` - Your OpenAI API key (if using GPT models)
- `MCP_AUTH_TOKEN` - Bearer token for your MCP service
- `TEST_DATABASE_URL` - Database connection string (if needed)

### 3. Customize for Your Service

Update the workflow files to match your MCP service setup:

#### If your MCP service is in the same repo:

```yaml
- name: Start MCP service
  run: |
    python -m your_mcp_service.server &
    echo $! > mcp_service.pid
```

#### If using Docker:

```yaml
- name: Start MCP service
  run: |
    docker-compose -f docker-compose.test.yml up -d
```

#### If using external service:

```yaml
env:
  MCP_URL: ${{ secrets.EXTERNAL_MCP_URL }}
```

### 4. Adjust Test Paths

Make sure the test paths match your repository structure:

```yaml
# If tests are in a different location
testmcpy run mcp_tests/tests/ --verbose

# Or specific files
testmcpy run tests/critical_tests.yaml
```

## Advanced Configuration

### Testing Multiple Models

Compare how different LLM models perform with your MCP service:

```yaml
strategy:
  matrix:
    model:
      - { provider: anthropic, name: claude-haiku-4-5 }
      - { provider: anthropic, name: claude-sonnet-4-5 }
      - { provider: openai, name: gpt-4-turbo }
      - { provider: openai, name: gpt-4o-mini }
```

### Cost Control

To minimize API costs:

1. **Use cheaper models for PRs**:
   ```yaml
   DEFAULT_MODEL: claude-haiku-4-5  # Fast and cheap
   ```

2. **Use better models only for main branch**:
   ```yaml
   test-with-sonnet:
     if: github.ref == 'refs/heads/main'
   ```

3. **Use local models for development**:
   ```yaml
   DEFAULT_PROVIDER: ollama
   DEFAULT_MODEL: llama3.1:8b
   ```

### Scheduled Tests

Run regression tests daily:

```yaml
# GitHub Actions
on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC

# GitLab CI
daily-tests:
  only:
    - schedules
```

Then configure the schedule in your platform's UI.

### Conditional Execution

Run tests only when relevant files change:

```yaml
# GitHub Actions
on:
  push:
    paths:
      - 'src/**'
      - 'tests/**'
      - '.github/workflows/mcp-tests.yml'

# GitLab CI
test-mcp:
  only:
    changes:
      - src/**/*
      - tests/**/*
```

### Parallel Execution

Speed up tests by running them in parallel:

```yaml
# GitHub Actions
strategy:
  matrix:
    test-suite:
      - basic
      - advanced
      - edge-cases

steps:
  - run: testmcpy run tests/${{ matrix.test-suite }}.yaml
```

### Test Result Notifications

#### Slack Notifications

```yaml
# GitHub Actions
- name: Notify Slack
  if: failure()
  uses: slackapi/slack-github-action@v1
  with:
    payload: |
      {
        "text": "MCP tests failed on ${{ github.ref }}"
      }
  env:
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK }}
```

#### Email Notifications

Most CI platforms support email notifications natively. Configure in Settings.

## Environment-Specific Configuration

### Development Environment

```yaml
# .env.dev
MCP_URL=http://localhost:5008/mcp/
DEFAULT_MODEL=claude-haiku-4-5  # Cheap for rapid testing
```

### Staging Environment

```yaml
# .env.staging
MCP_URL=https://staging.example.com/mcp/
DEFAULT_MODEL=claude-sonnet-4-5  # Better accuracy for staging
```

### Production-like Environment

```yaml
# .env.prod-like
MCP_URL=https://test.example.com/mcp/
DEFAULT_MODEL=claude-sonnet-4-5
```

## Troubleshooting CI/CD

### Tests timeout

Increase timeout in workflow:

```yaml
timeout-minutes: 30  # Default is 360 (6 hours)
```

And in test files:

```yaml
tests:
  - name: "slow_test"
    timeout: 60  # seconds
```

### Service not ready

Add better health checks:

```yaml
- name: Wait for service with retries
  run: |
    for i in {1..30}; do
      if curl -f http://localhost:5008/health; then
        echo "Service ready"
        exit 0
      fi
      echo "Attempt $i/30 failed, waiting..."
      sleep 2
    done
    echo "Service failed to start"
    exit 1
```

### Rate limiting

Use rate limit protection:

```yaml
- name: Run tests with delays
  run: |
    testmcpy run tests/test1.yaml
    sleep 60
    testmcpy run tests/test2.yaml
```

Or use local models:

```yaml
DEFAULT_PROVIDER: ollama
DEFAULT_MODEL: llama3.1:8b
```

### Secrets not available

Ensure secrets are:
1. Created in the correct repository
2. Named exactly as referenced in workflow
3. Available to the branch (check branch protection rules)

## Best Practices

1. **Start simple**: Begin with basic tests, add complexity gradually
2. **Use cheap models for PRs**: Save costs by using `claude-haiku-4-5` for pull request tests
3. **Run comprehensive tests on main**: Use better models like `claude-sonnet-4-5` for main branch
4. **Cache dependencies**: Use pip caching to speed up builds
5. **Fail fast**: Use `fail-fast: false` in matrix to test all models even if one fails
6. **Keep secrets secure**: Always use CI/CD secrets, never hardcode credentials
7. **Monitor costs**: Track API usage in your LLM provider dashboard
8. **Archive results**: Keep test results for debugging and trend analysis

## Example: Complete CI/CD Workflow

See our production setup in the testmcpy repository:
- GitHub: `.github/workflows/test.yml`
- Uses matrix testing across models
- Uploads artifacts for debugging
- Posts results to PRs

## Support

For CI/CD integration help:
- GitHub Discussions: https://github.com/preset-io/testmcpy/discussions
- Issues: https://github.com/preset-io/testmcpy/issues
