import React from 'react'
import { GitCompare, Play } from 'lucide-react'
import MCPProfileSelector from './MCPProfileSelector'
import ToolComparison from './ToolComparison'

const CompareToolsTab = ({
  tools,
  compareToolName,
  setCompareToolName,
  compareProfile1,
  setCompareProfile1,
  compareProfile2,
  setCompareProfile2,
  compareParameters,
  setCompareParameters,
  compareIterations,
  setCompareIterations,
  runningComparison,
  runComparison,
  comparisonResults,
  setComparisonResults,
}) => {
  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {!comparisonResults ? (
        <div className="bg-surface-elevated border border-border rounded-lg p-6">
          <h2 className="text-xl font-bold text-text-primary mb-6 flex items-center gap-2">
            <GitCompare size={24} />
            Compare Tool Performance
          </h2>
          <div className="space-y-6">
            {/* Tool Selection */}
            <div>
              <label className="block text-sm font-medium text-text-primary mb-2">
                Tool to Compare
              </label>
              <select
                value={compareToolName}
                onChange={(e) => setCompareToolName(e.target.value)}
                className="input w-full"
              >
                <option value="">Select a tool...</option>
                {tools.map((tool) => (
                  <option key={tool.name} value={tool.name}>
                    {tool.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Profile/Server Selection */}
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-text-primary mb-2">
                  Profile/Server 1
                </label>
                <MCPProfileSelector
                  selectedProfiles={compareProfile1}
                  onChange={setCompareProfile1}
                  multiple={false}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-text-primary mb-2">
                  Profile/Server 2
                </label>
                <MCPProfileSelector
                  selectedProfiles={compareProfile2}
                  onChange={setCompareProfile2}
                  multiple={false}
                />
              </div>
            </div>

            {/* Parameters */}
            <div>
              <label className="block text-sm font-medium text-text-primary mb-2">
                Tool Parameters (JSON)
              </label>
              <textarea
                value={compareParameters}
                onChange={(e) => setCompareParameters(e.target.value)}
                className="input w-full font-mono text-sm"
                rows={6}
                placeholder='{"param1": "value1", "param2": "value2"}'
              />
            </div>

            {/* Iterations */}
            <div>
              <label className="block text-sm font-medium text-text-primary mb-2">
                Iterations: {compareIterations}
              </label>
              <input
                type="range"
                min="1"
                max="20"
                value={compareIterations}
                onChange={(e) => setCompareIterations(parseInt(e.target.value))}
                className="w-full"
              />
              <div className="flex justify-between text-xs text-text-tertiary mt-1">
                <span>1</span>
                <span>10</span>
                <span>20</span>
              </div>
            </div>

            {/* Run Button */}
            <button
              onClick={runComparison}
              disabled={runningComparison}
              className="btn btn-primary w-full"
            >
              {runningComparison ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  <span>Running Comparison...</span>
                </>
              ) : (
                <>
                  <Play size={16} />
                  <span>Run Comparison</span>
                </>
              )}
            </button>
          </div>
        </div>
      ) : (
        <>
          <button
            onClick={() => setComparisonResults(null)}
            className="btn btn-secondary"
          >
            New Comparison
          </button>
          <ToolComparison comparisonResults={comparisonResults} />
        </>
      )}
    </div>
  )
}

export default CompareToolsTab
