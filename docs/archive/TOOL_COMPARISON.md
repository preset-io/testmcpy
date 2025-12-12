# MCP Tool Comparison Feature

The `compare-tool` command allows you to benchmark and compare the same MCP tool across different sources to:

- Identify performance differences between environments (staging vs production)
- Compare different MCP server implementations
- Test tool behavior consistency across configurations
- Benchmark tool execution times and success rates

## Overview

The tool comparison feature executes the same MCP tool multiple times on two different sources and provides detailed metrics including:

- **Success Rate**: Percentage of successful executions
- **Execution Time Statistics**: Min, Max, Average, and Median execution times
- **Response Comparison**: Whether responses match between sources
- **Detailed Results**: Full execution data for each iteration

## Usage

### Basic Command Structure

```bash
testmcpy compare-tool <tool-name> \
  --profile1 <profile1> --profile2 <profile2> \
  --params '{"key": "value"}' \
  --iterations <number> \
  --output <output-file.json>
```

### Required Arguments

- `tool-name`: Name of the MCP tool to compare (e.g., `get_chart`, `list_dashboards`)

### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--profile1` | | First MCP profile from `.mcp_services.yaml` | None |
| `--profile2` | | Second MCP profile from `.mcp_services.yaml` | None |
| `--mcp-url1` | | First MCP service URL (overrides profile1) | None |
| `--mcp-url2` | | Second MCP service URL (overrides profile2) | None |
| `--mcp-name1` | | Specific MCP server name within profile1 | None |
| `--mcp-name2` | | Specific MCP server name within profile2 | None |
| `--params` | | Tool parameters as JSON string | `{}` |
| `--iterations` | `-n` | Number of iterations to run | `5` |
| `--output` | `-o` | Output file for results (JSON) | None |
| `--timeout` | | Timeout for each tool call in seconds | `30.0` |

## Examples

### Example 1: Compare Tool Across Profiles

Compare the `get_chart` tool between staging and production environments:

```bash
testmcpy compare-tool get_chart \
  --profile1 staging \
  --profile2 prod \
  --params '{"chart_id": 123}' \
  --iterations 10
```

**Output:**
```
┌─────────────────────────┬────────────────────┬────────────────────┬─────────────────┐
│ Metric                  │          Source 1  │          Source 2  │      Difference │
├─────────────────────────┼────────────────────┼────────────────────┼─────────────────┤
│ Source                  │ Profile: staging   │ Profile: prod      │                 │
│ Success Rate            │              100.0%│              100.0%│           +0.0% │
│ Successful              │                10/10│                10/10│                 │
│                         │                    │                    │                 │
│ Avg Execution Time      │              0.342s│              0.298s│          -0.044s│
│ Median Time             │              0.338s│              0.295s│          -0.043s│
│ Min Time                │              0.312s│              0.278s│                 │
│ Max Time                │              0.389s│              0.324s│                 │
└─────────────────────────┴────────────────────┴────────────────────┴─────────────────┘

Response Comparison:
✓ Responses match
```

### Example 2: Compare with Direct URLs

Compare the same tool across two different MCP servers using direct URLs:

```bash
testmcpy compare-tool list_dashboards \
  --mcp-url1 http://server1.example.com/mcp \
  --mcp-url2 http://server2.example.com/mcp \
  --iterations 5 \
  --output comparison-results.json
```

### Example 3: Compare Specific MCP Servers Within Profiles

If a profile contains multiple MCP servers, you can specify which ones to compare:

```bash
testmcpy compare-tool get_data \
  --profile1 prod \
  --mcp-name1 superset-api \
  --profile2 prod \
  --mcp-name2 superset-api-v2 \
  --params '{"dataset_id": 456}' \
  --iterations 20
```

### Example 4: Save Results to File

Save detailed comparison results to a JSON file for later analysis:

```bash
testmcpy compare-tool get_dashboard \
  --profile1 staging \
  --profile2 prod \
  --params '{"dashboard_id": 789}' \
  --iterations 15 \
  --output dashboard-comparison.json
```

## Output Format

### Console Output

The command displays:

1. **Configuration Table**: Shows the comparison setup
2. **Progress Indicator**: Real-time progress during execution
3. **Results Table**: Side-by-side comparison with metrics
4. **Response Comparison**: Indicates whether responses match

### JSON Output

When using `--output`, the JSON file contains:

```json
{
  "tool_name": "get_chart",
  "tool_params": {
    "chart_id": 123
  },
  "iterations": 10,
  "source1": {
    "name": "Profile: staging / MCP: Superset MCP",
    "stats": {
      "min_time": 0.312,
      "max_time": 0.389,
      "avg_time": 0.342,
      "median_time": 0.338,
      "success_rate": 1.0,
      "total_executions": 10,
      "successful_executions": 10,
      "failed_executions": 0
    },
    "executions": [
      {
        "success": true,
        "execution_time": 0.342,
        "response_content": { ... },
        "error_message": null
      },
      ...
    ]
  },
  "source2": {
    "name": "Profile: prod / MCP: Superset MCP",
    "stats": { ... },
    "executions": [ ... ]
  },
  "comparison": {
    "responses_match": true,
    "response_diff": null
  }
}
```

## Use Cases

### 1. Performance Benchmarking

Compare execution times between different environments:

```bash
testmcpy compare-tool expensive_query \
  --profile1 staging \
  --profile2 prod \
  --params '{"complex_filter": true}' \
  --iterations 50
```

### 2. Reliability Testing

Test success rates across environments:

```bash
testmcpy compare-tool flaky_operation \
  --profile1 server1 \
  --profile2 server2 \
  --iterations 100
```

### 3. API Version Comparison

Compare behavior between API versions:

```bash
testmcpy compare-tool get_user \
  --mcp-url1 http://api.example.com/v1/mcp \
  --mcp-url2 http://api.example.com/v2/mcp \
  --params '{"user_id": 123}' \
  --iterations 10
```

### 4. Migration Validation

Validate that a new implementation matches the old one:

```bash
testmcpy compare-tool legacy_endpoint \
  --profile1 old-system \
  --profile2 new-system \
  --params '{"id": 456}' \
  --iterations 25 \
  --output migration-validation.json
```

## Configuration

### Using Profiles

Configure profiles in `.mcp_services.yaml`:

```yaml
default: staging

profiles:
  staging:
    name: Staging Environment
    mcps:
      - name: Superset Staging
        default: true
        mcp_url: https://staging.example.com/mcp
        auth:
          type: jwt
          api_url: https://api.staging.example.com/auth
          api_token: ${STAGING_TOKEN}
          api_secret: ${STAGING_SECRET}

  prod:
    name: Production Environment
    mcps:
      - name: Superset Production
        default: true
        mcp_url: https://prod.example.com/mcp
        auth:
          type: jwt
          api_url: https://api.prod.example.com/auth
          api_token: ${PROD_TOKEN}
          api_secret: ${PROD_SECRET}
```

### Authentication

The comparison tool supports all authentication types:

- **Bearer Token**: Direct token authentication
- **JWT**: Dynamic JWT fetching from API
- **OAuth**: OAuth client credentials flow
- **None**: No authentication

Authentication is configured per MCP server in the profile.

## Metrics Explained

### Success Rate
Percentage of executions that completed without errors. A 100% success rate indicates perfect reliability.

### Execution Time Statistics

- **Min Time**: Fastest execution (best-case scenario)
- **Max Time**: Slowest execution (worst-case scenario)
- **Avg Time**: Average execution time across all iterations
- **Median Time**: Middle value when execution times are sorted (better representation when outliers exist)

### Response Comparison

The tool compares responses from the first successful execution of each source:
- **Match**: Responses are identical
- **Differ**: Responses vary (may include type information)

## Best Practices

1. **Use Adequate Iterations**: Run at least 10-20 iterations for reliable statistics
2. **Consider Timeout**: Set appropriate timeout values for slow operations
3. **Save Results**: Use `--output` to preserve results for historical comparison
4. **Test Parameters**: Use realistic parameters that represent actual usage
5. **Monitor Patterns**: Look for patterns like consistently slower execution or intermittent failures

## Troubleshooting

### "Profile not found" Error

Ensure your `.mcp_services.yaml` file exists and contains the specified profiles:

```bash
# Check available profiles
testmcpy profiles list
```

### "Tool not found" Error

Verify the tool exists on both MCP servers:

```bash
# List tools in profile
testmcpy list-tools --profile staging
testmcpy list-tools --profile prod
```

### Authentication Failures

Check that your authentication credentials are valid:

```bash
# Debug authentication
testmcpy debug-auth --profile staging
```

### Timeout Errors

Increase the timeout for slow operations:

```bash
testmcpy compare-tool slow_query \
  --profile1 staging \
  --profile2 prod \
  --timeout 60.0
```

## Integration with CI/CD

You can integrate tool comparison into your CI/CD pipeline:

```yaml
# GitHub Actions example
- name: Compare MCP Tools
  run: |
    testmcpy compare-tool get_chart \
      --profile1 staging \
      --profile2 prod \
      --params '{"chart_id": 123}' \
      --iterations 10 \
      --output comparison-results.json

- name: Check Success Rate
  run: |
    python -c "
    import json
    with open('comparison-results.json') as f:
        data = json.load(f)
        if data['source2']['stats']['success_rate'] < 0.95:
            print('Production success rate below 95%!')
            exit(1)
    "
```

## Implementation Details

The tool comparison feature:

- Creates two independent MCP client connections
- Executes tools sequentially to avoid concurrency issues
- Measures execution time for each call
- Captures all responses for comparison
- Calculates statistical metrics
- Provides color-coded output for easy interpretation

## Related Commands

- `testmcpy list-tools`: List available MCP tools
- `testmcpy call-tool`: Execute a single tool call
- `testmcpy profiles list`: List configured profiles
- `testmcpy debug-auth`: Debug authentication issues
