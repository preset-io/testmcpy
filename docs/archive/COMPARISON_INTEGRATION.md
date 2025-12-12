# Integration Instructions for Tool Comparison Feature

## Changes to MCPExplorer.jsx

### 1. Add imports at the top of the file (after line 8):

```javascript
import CompareToolsTab from '../components/CompareToolsTab'
```

### 2. Add state variables for comparison (after line 30, after `runningTests` state):

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

### 3. Add comparison function (after line 343, after `filterPrompts` function):

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

### 4. Add Compare tab button (after line 524, after Prompts tab button):

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

### 5. Add Compare tab content (after line 954, after the prompts tab closing):

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

## Files Created

1. `/Users/amin/github/preset-io/testmcpy/testmcpy/ui/src/components/ToolComparison.jsx` - Component to display comparison results
2. `/Users/amin/github/preset-io/testmcpy/testmcpy/ui/src/components/CompareToolsTab.jsx` - Tab content for the comparison UI

## Next Steps

1. Apply the changes to MCPExplorer.jsx as outlined above
2. ~~Implement the API endpoint `/api/tools/compare` in `testmcpy/server/api.py`~~ DONE
3. Test the integration

## Status

- API Endpoint: IMPLEMENTED (lines 2892-3016 in api.py)
- Request Model: IMPLEMENTED (ToolCompareRequest in api.py)
- React Components: CREATED (ToolComparison.jsx, CompareToolsTab.jsx)
- MCPExplorer Integration: NEEDS MANUAL APPLICATION (see instructions above)

The linter was preventing direct edits to MCPExplorer.jsx, so the integration needs to be applied manually following the instructions in sections 1-5 above.
