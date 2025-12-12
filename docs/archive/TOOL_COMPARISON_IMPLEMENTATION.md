# Tool Comparison/Benchmarking Feature Implementation

## Overview

A comprehensive tool comparison feature has been implemented for the testmcpy Web UI that allows users to compare the performance and behavior of MCP tools across different profiles/servers.

## Features Implemented

### 1. Compare Mode in Explorer Page
- New "Compare" tab alongside Tools, Resources, and Prompts
- UI for selecting tool and two MCP profiles/servers to compare
- Parameter input (JSON format)
- Iterations slider (1-20)
- Real-time comparison execution

### 2. Side-by-Side Results Display
- Two-column layout showing results from both profiles
- Performance metrics:
  - Average response time
  - Success rate
  - Time comparison (faster/slower with percentage)
- Individual iteration results with:
  - Success/failure status
  - Response time
  - Full response output (JSON formatted)
  - Error messages (if failed)

### 3. API Endpoint
- `POST /api/tools/compare` endpoint
- Accepts:
  - Tool name
  - Two profile/server IDs (format: "profile_id:mcp_name")
  - Parameters (JSON object)
  - Number of iterations
- Returns:
  - Results from both profiles
  - Calculated metrics
  - Performance comparison

### 4. Visual Design
- Color-coded performance indicators (green for faster, red for slower)
- Success/error badges
- Collapsible sections
- Download results as JSON button
- Responsive design

## Files Created

### React Components

1. **`/Users/amin/github/preset-io/testmcpy/testmcpy/ui/src/components/ToolComparison.jsx`**
   - Main component for displaying comparison results
   - Side-by-side layout with metrics cards
   - Individual iteration results with formatted JSON output
   - Download functionality

2. **`/Users/amin/github/preset-io/testmcpy/testmcpy/ui/src/components/CompareToolsTab.jsx`**
   - Tab content for the comparison UI
   - Tool selection dropdown
   - Profile/server selectors (2)
   - Parameter input (JSON textarea)
   - Iterations slider
   - Run comparison button

### Backend

3. **`/Users/amin/github/preset-io/testmcpy/testmcpy/server/api.py`**
   - Added `ToolCompareRequest` Pydantic model (lines 210-215)
   - Added `POST /api/tools/compare` endpoint (lines 2892-3016)
   - Implements:
     - Profile loading and validation
     - MCP client initialization per iteration
     - Tool execution with timing
     - Metrics calculation
     - Error handling

## Integration Instructions

### MCPExplorer.jsx Changes

The following changes need to be manually applied to `/Users/amin/github/preset-io/testmcpy/testmcpy/ui/src/pages/MCPExplorer.jsx`:

#### 1. Add import (after line 8):
```javascript
import CompareToolsTab from '../components/CompareToolsTab'
```

#### 2. Add GitCompare icon to lucide-react imports (line 2):
```javascript
import { ..., GitCompare } from 'lucide-react'
```

#### 3. Add state variables (after line 30):
```javascript
// Comparison mode state
const [compareProfile1, setCompareProfile1] = useState([])
const [compareProfile2, setCompareProfile2] = useState([])
const [compareToolName, setCompareToolName] = useState('')
const [compareParameters, setCompareParameters] = useState('{}')
const [compareIterations, setCompareIterations] = useState(3)
const [comparisonResults, setComparisonResults] = useState(null)
const [runningComparison, setRunningComparison] = useState(false)
```

#### 4. Add comparison function (after line 343):
```javascript
// Run tool comparison
const runComparison = async () => {
  if (!compareToolName.trim()) {
    alert('Please select a tool to compare')
    return
  }
  if (compareProfile1.length === 0 || compareProfile2.length === 0) {
    alert('Please select two profiles/servers to compare')
    return
  }
  if (compareProfile1[0] === compareProfile2[0]) {
    alert('Please select two different profiles/servers')
    return
  }

  let parameters = {}
  try {
    parameters = JSON.parse(compareParameters)
  } catch (e) {
    alert('Invalid JSON in parameters field')
    return
  }

  setRunningComparison(true)
  setComparisonResults(null)

  try {
    const response = await fetch('/api/tools/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tool_name: compareToolName,
        profile1: compareProfile1[0],
        profile2: compareProfile2[0],
        parameters: parameters,
        iterations: compareIterations,
      }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Comparison failed')
    }

    const data = await response.json()
    setComparisonResults(data)
  } catch (error) {
    console.error('Comparison error:', error)
    alert(`Comparison failed: ${error.message}`)
  } finally {
    setRunningComparison(false)
  }
}
```

#### 5. Add Compare tab button (after line 524):
```javascript
<button
  onClick={() => {
    setActiveTab('compare')
    setComparisonResults(null)
  }}
  className={`tab ${
    activeTab === 'compare' ? 'tab-active' : 'tab-inactive'
  }`}
>
  <GitCompare size={16} className="mr-1" />
  Compare
</button>
```

#### 6. Add Compare tab content (after line 954, before the closing `</div>`):
```javascript
{activeTab === 'compare' && (
  <CompareToolsTab
    tools={tools}
    compareToolName={compareToolName}
    setCompareToolName={setCompareToolName}
    compareProfile1={compareProfile1}
    setCompareProfile1={setCompareProfile1}
    compareProfile2={compareProfile2}
    setCompareProfile2={setCompareProfile2}
    compareParameters={compareParameters}
    setCompareParameters={setCompareParameters}
    compareIterations={compareIterations}
    setCompareIterations={setCompareIterations}
    runningComparison={runningComparison}
    runComparison={runComparison}
    comparisonResults={comparisonResults}
    setComparisonResults={setComparisonResults}
  />
)}
```

## Usage

### From the UI:

1. Navigate to Explorer page
2. Click the "Compare" tab
3. Select a tool to compare
4. Select two different MCP profiles/servers
5. Enter tool parameters as JSON (or leave as `{}`)
6. Adjust iterations slider (default: 3)
7. Click "Run Comparison"
8. View side-by-side results with performance metrics
9. Optionally download results as JSON

### API Example:

```bash
curl -X POST http://localhost:8000/api/tools/compare \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "get_weather",
    "profile1": "local-dev:weather-api-1",
    "profile2": "production:weather-api-2",
    "parameters": {"city": "San Francisco"},
    "iterations": 5
  }'
```

### Response Format:

```json
{
  "tool_name": "get_weather",
  "profile1": "Local Development (weather-api-1)",
  "profile2": "Production (weather-api-2)",
  "parameters": {"city": "San Francisco"},
  "iterations": 5,
  "results1": [
    {
      "iteration": 1,
      "success": true,
      "result": {...},
      "error": null,
      "duration_ms": 145.2
    },
    ...
  ],
  "results2": [...],
  "metrics": {
    "avg_time1_ms": 142.5,
    "avg_time2_ms": 238.7,
    "success_rate1_pct": 100.0,
    "success_rate2_pct": 100.0,
    "faster_profile": 1,
    "time_difference_ms": 96.2,
    "time_difference_pct": 40.3
  }
}
```

## Technical Details

### Backend Implementation

- Uses async/await for non-blocking tool execution
- Initializes separate MCP clients for each iteration to ensure isolation
- Properly cleans up clients after each iteration
- Calculates real-time metrics including:
  - Average response time
  - Success rate percentage
  - Performance difference (absolute and percentage)
- Handles errors gracefully with detailed error messages

### Frontend Implementation

- Uses React hooks for state management
- MCPProfileSelector component for profile selection
- Responsive grid layout for side-by-side comparison
- Color-coded visual indicators for performance differences
- JSON formatting for parameter input and result display
- Loading states during comparison execution

## Benefits

1. **Performance Analysis**: Compare tool execution times across different servers
2. **Reliability Testing**: Compare success rates and error patterns
3. **A/B Testing**: Test different MCP server configurations
4. **Migration Planning**: Validate new server deployments before cutover
5. **Debugging**: Identify performance bottlenecks and inconsistencies

## Future Enhancements (Potential)

- Support for comparing more than 2 profiles
- Historical comparison results storage
- Charts/graphs for visualizing performance over multiple iterations
- Automatic retry logic for failed iterations
- Export to CSV format
- Diff viewer for highlighting response differences
- Batch comparison (multiple tools at once)
- Scheduled/automated comparisons

## Testing Checklist

- [ ] Verify Compare tab appears in Explorer
- [ ] Test tool selection dropdown
- [ ] Test profile selector for both profiles
- [ ] Test parameter input validation (JSON)
- [ ] Test iterations slider (1-20)
- [ ] Test comparison execution with valid inputs
- [ ] Test error handling (invalid profiles, tool not found, etc.)
- [ ] Verify results display correctly
- [ ] Test download JSON functionality
- [ ] Test "New Comparison" button
- [ ] Verify responsive design on different screen sizes
- [ ] Test with successful tool executions
- [ ] Test with failing tool executions
- [ ] Test with mixed success/failure results

## Files Modified

1. `/Users/amin/github/preset-io/testmcpy/testmcpy/server/api.py` - Added comparison endpoint
2. `/Users/amin/github/preset-io/testmcpy/testmcpy/ui/src/pages/MCPExplorer.jsx` - Needs manual integration

## Files Created

1. `/Users/amin/github/preset-io/testmcpy/testmcpy/ui/src/components/ToolComparison.jsx`
2. `/Users/amin/github/preset-io/testmcpy/testmcpy/ui/src/components/CompareToolsTab.jsx`
3. `/Users/amin/github/preset-io/testmcpy/COMPARISON_INTEGRATION.md`
4. `/Users/amin/github/preset-io/testmcpy/TOOL_COMPARISON_IMPLEMENTATION.md` (this file)
5. `/Users/amin/github/preset-io/testmcpy/testmcpy/server/tool_compare_endpoint.py` (reference)
