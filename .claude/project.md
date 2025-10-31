# testmcpy UI/UX Modernization Plan

## Current Issues Identified

### 1. Space Efficiency Problems
- **Sidebar (w-64/256px)**: Too wide for nav-only purpose, wastes horizontal space
- **Header sections (p-8/32px)**: Overly padded, reduces content area
- **Bottom input bar (p-6/24px)**: Takes up too much vertical space
- **Connection status card**: Takes significant space in collapsed sidebar

### 2. Chat Interface Issues
- **Content-driven width**: Messages at `max-w-[85%]` cause layout shifts with variable content
- **Input area layout**: Large textarea (3 rows) + padding wastes space
- **Message bubbles**: Too much padding (p-5/20px) reduces message density
- **Metadata display**: Token/cost info takes up full row, could be condensed

### 3. Schema Viewer Problems
- **Raw JSON dump**: Shows entire schema as unformatted JSON in MCPExplorer.jsx:199-201
- **No visual hierarchy**: Parameters displayed in flat list without grouping
- **Type information**: Basic badges don't convey complexity (arrays, nested objects)
- **No examples**: Missing example values or default values
- **Poor collapsibility**: Everything expands/collapses together

### 4. Test Runner Status
- **Text-only feedback**: "Running..." button text is only indicator (TestManager.jsx:350)
- **No progress visualization**: Can't see which test is running
- **Console-dependent**: Says "Check the console" instead of showing in UI (TestManager.jsx:382)
- **Results appear suddenly**: No smooth transition or loading skeleton
- **Missing IDE-like features**: No line highlighting, no test markers, no inline results

---

## Modernization Plan

## Phase 1: Space Optimization (Quick Wins)

### 1.1 Slim Down Sidebar
**Goal**: Reduce from 256px to 200px, optimize spacing

```jsx
// App.jsx changes
- w-64 (256px) → w-50 (200px)
- p-4 → p-3 (reduce padding)
- Status card: Simplify, remove decorative elements
```

**Specific changes**:
- Reduce nav item padding from `py-2.5` to `py-2`
- Connection status: Show as compact badge instead of card
- Version info: Move to hover tooltip instead of persistent display

### 1.2 Compress Headers
**Goal**: Reduce vertical space, keep breathing room

```jsx
// All pages: ChatInterface, MCPExplorer, TestManager
- p-8 → p-4 (header padding 32px → 16px)
- text-3xl → text-2xl (title size)
- mt-2 → mt-1 (subtitle margin)
```

### 1.3 Optimize Input Area
**Goal**: More compact, still usable

```jsx
// ChatInterface.jsx:617-636
- p-6 → p-3 (reduce padding)
- rows={3} → rows={1} (start with single line)
- Auto-expand on content (like Slack/Discord)
- Reduce button padding
```

---

## Phase 2: Chat Interface Improvements

### 2.1 Fixed-Width Message Container
**Problem**: Content width drives container width causing layout shifts

**Solution**:
```jsx
// ChatInterface.jsx:388-614
// Instead of max-w-[85%], use fixed container with word-wrap
<div className="space-y-4 max-w-3xl mx-auto">
  {messages.map((message, idx) => (
    <div className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
      <div className={`w-full max-w-2xl rounded-lg p-3 ...`}>
        {/* Message content with break-words */}
      </div>
    </div>
  ))}
</div>
```

### 2.2 Compact Message Layout
- Reduce message padding: `p-5` → `p-3`
- Inline metadata: Put tokens/cost/time on same line with icons
- Collapsible tool calls by default
- Smaller font for metadata: `text-xs` → `text-[10px]`

### 2.3 Better Input UX
```jsx
// Auto-expanding textarea
- Starts at 1 row
- Expands to max 6 rows as user types
- Cmd/Ctrl+Enter to send (show hint)
- Compact send button (icon only on small screens)
```

---

## Phase 3: Schema Viewer Redesign

### 3.1 Smart Parameter Display
**Replace raw JSON with structured UI**:

```jsx
// MCPExplorer.jsx: Replace lines 195-202
<div className="space-y-2">
  <h4 className="text-sm font-semibold mb-2">Parameters</h4>
  {Object.entries(schema.properties).map(([name, prop]) => (
    <ParameterCard
      name={name}
      type={prop.type}
      required={schema.required?.includes(name)}
      description={prop.description}
      default={prop.default}
      enum={prop.enum}
      items={prop.items} // for arrays
      properties={prop.properties} // for nested objects
    />
  ))}
</div>
```

### 3.2 Type Visualization
**Visual indicators for parameter types**:

```jsx
// Color-coded type badges
- string: blue badge with "Abc" icon
- number/integer: green badge with "123" icon
- boolean: purple badge with toggle icon
- array: yellow badge with list icon + item type
- object: pink badge with {} icon (expandable)
- enum: orange badge with dropdown icon + count
```

### 3.3 Nested Schema Rendering
**Recursive component for objects/arrays**:

```jsx
<ParameterCard>
  {type === 'object' && (
    <Collapsible>
      <div className="ml-4 border-l-2 border-border pl-3">
        {/* Recursively render nested properties */}
      </div>
    </Collapsible>
  )}

  {type === 'array' && (
    <div className="ml-4">
      <TypeBadge type={items.type} label="Array items" />
    </div>
  )}
</ParameterCard>
```

### 3.4 Example Values
```jsx
// Show default values and examples
{prop.default && (
  <div className="text-xs text-text-tertiary mt-1">
    Default: <code className="font-mono bg-surface px-1 rounded">{prop.default}</code>
  </div>
)}

{prop.enum && (
  <div className="text-xs text-text-tertiary mt-1">
    Options: {prop.enum.join(' | ')}
  </div>
)}
```

### 3.5 JSON View Toggle
```jsx
// Keep raw JSON as collapsible option
<button onClick={() => setShowRaw(!showRaw)} className="text-xs text-text-tertiary">
  {showRaw ? 'Hide' : 'Show'} Raw JSON
</button>
```

---

## Phase 4: IDE-Style Test Runner

### 4.1 Visual Test Execution Status
**Replace text-only "Running..." with visual progress**:

```jsx
// TestManager.jsx: Add test execution state
const [runningTests, setRunningTests] = useState({
  current: null,    // Current test name
  total: 0,         // Total tests
  completed: 0,     // Completed tests
  status: 'idle'    // 'idle' | 'running' | 'done'
})

// Visual indicator
{runningTests.status === 'running' && (
  <div className="border-t border-border p-3 bg-surface-elevated">
    <div className="flex items-center gap-3 mb-2">
      <div className="animate-spin rounded-full h-4 w-4 border-2 border-primary border-t-transparent"></div>
      <span className="text-sm font-medium">Running Tests</span>
      <span className="text-xs text-text-tertiary">
        {runningTests.completed} / {runningTests.total}
      </span>
    </div>

    {/* Progress bar */}
    <div className="h-1.5 bg-surface-elevated rounded-full overflow-hidden">
      <div
        className="h-full bg-primary transition-all duration-300"
        style={{ width: `${(runningTests.completed / runningTests.total) * 100}%` }}
      />
    </div>

    {/* Current test */}
    {runningTests.current && (
      <div className="text-xs text-text-tertiary mt-2 flex items-center gap-2">
        <Loader size={12} className="animate-spin" />
        <span>Running: {runningTests.current}</span>
      </div>
    )}
  </div>
)}
```

### 4.2 Inline Test Status Markers
**Show test status in editor gutter (like IDE breakpoints)**:

```jsx
// Add custom Monaco editor decorations
const updateTestDecorations = (results) => {
  const decorations = results.map((result, idx) => ({
    range: new monaco.Range(getTestLineNumber(result.test_name), 1, getTestLineNumber(result.test_name), 1),
    options: {
      isWholeLine: false,
      glyphMarginClassName: result.passed
        ? 'test-glyph-pass'  // Green checkmark CSS
        : 'test-glyph-fail', // Red X CSS
      glyphMarginHoverMessage: { value: result.reason }
    }
  }))

  editor.deltaDecorations([], decorations)
}

// CSS for glyphs
.test-glyph-pass::before {
  content: '✓';
  color: #10b981;
  font-weight: bold;
}

.test-glyph-fail::before {
  content: '✗';
  color: #ef4444;
  font-weight: bold;
}
```

### 4.3 Live Test Output Stream
**Show test output as it runs (not just final results)**:

```jsx
// Add WebSocket or SSE connection for live updates
const [testLogs, setTestLogs] = useState([])

// During test run, show logs in bottom panel
<div className="border-t border-border max-h-64 overflow-auto font-mono text-xs bg-black/50 p-3">
  {testLogs.map((log, idx) => (
    <div key={idx} className={`${
      log.level === 'error' ? 'text-error' :
      log.level === 'success' ? 'text-success' :
      'text-text-tertiary'
    }`}>
      <span className="text-text-disabled">[{log.timestamp}]</span> {log.message}
    </div>
  ))}
</div>
```

### 4.4 Results as Split View
**Show results in split panel instead of pushing editor up**:

```jsx
// TestManager.jsx: Change layout to split view
<div className="flex-1 flex flex-col">
  {/* Editor area */}
  <div className={`${testResults ? 'h-1/2' : 'flex-1'} transition-all duration-300`}>
    <Editor />
  </div>

  {/* Results panel (slides up from bottom) */}
  {testResults && (
    <div className="h-1/2 border-t border-border overflow-auto animate-slide-up">
      <TestResults results={testResults} />
    </div>
  )}
</div>
```

### 4.5 Test Result Details
**Expandable details per test**:

```jsx
<div className="space-y-2">
  {results.map((result) => (
    <div className="border border-border rounded-lg">
      {/* Header (always visible) */}
      <div
        className="p-3 flex items-center justify-between cursor-pointer hover:bg-surface-hover"
        onClick={() => toggleExpand(result.test_name)}
      >
        <div className="flex items-center gap-2">
          {result.passed ? <CheckCircle size={16} className="text-success" /> : <XCircle size={16} className="text-error" />}
          <span className="font-medium text-sm">{result.test_name}</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-text-tertiary">
          <span>{result.duration.toFixed(2)}s</span>
          {result.cost > 0 && <span>${result.cost.toFixed(4)}</span>}
          <ChevronDown size={14} />
        </div>
      </div>

      {/* Details (collapsible) */}
      {expanded.has(result.test_name) && (
        <div className="border-t border-border p-3 bg-surface-elevated space-y-2">
          {/* Show LLM response */}
          {/* Show tool calls */}
          {/* Show evaluator breakdown */}
        </div>
      )}
    </div>
  ))}
</div>
```

---

## Phase 5: Design System Refinements

### 5.1 Spacing Scale
**Update base spacing to be more compact**:

```css
/* tailwind.config.js */
spacing: {
  // Reduce large spacing values
  '128': '28rem',  // was 32rem
  '144': '32rem',  // was 36rem
}
```

### 5.2 Typography Scale
**Slightly smaller headings**:

```css
fontSize: {
  '3xl': ['1.75rem', { lineHeight: '2rem' }],  // was 1.875rem
  '2xl': ['1.5rem', { lineHeight: '1.75rem' }], // was 1.5rem
}
```

### 5.3 Border Radius
**Slightly reduce roundness for more space**:

```css
borderRadius: {
  'lg': '0.5rem',   // was 0.5rem (keep)
  'xl': '0.75rem',  // was 0.75rem → 0.625rem
  '2xl': '1rem',    // was 1rem → 0.875rem
}
```

---

## Implementation Priority

### High Priority (Week 1)
1. ✅ Sidebar width reduction (App.jsx)
2. ✅ Header padding optimization (all pages)
3. ✅ Chat message layout fix (ChatInterface.jsx)
4. ✅ Input area compression (ChatInterface.jsx)

### Medium Priority (Week 2)
5. ⚠️ Schema viewer redesign (MCPExplorer.jsx)
6. ⚠️ Test runner visual status (TestManager.jsx)
7. ⚠️ Message container fixed width

### Lower Priority (Week 3)
8. ⏳ IDE-style test markers
9. ⏳ Live test output stream
10. ⏳ Split view test results

---

## Component Specifications

### New Components to Create

#### 1. `ParameterCard.jsx`
```jsx
/**
 * Smart parameter display with type visualization
 * Handles nested objects, arrays, enums
 */
<ParameterCard
  name="chart_id"
  type="integer"
  required={true}
  description="The ID of the chart to fetch"
  min={1}
  default={null}
/>
```

#### 2. `TypeBadge.jsx`
```jsx
/**
 * Visual type indicator with icon and color coding
 */
<TypeBadge type="string" />      // Blue with "Abc"
<TypeBadge type="array" items="integer" />  // Yellow with "[]"
```

#### 3. `TestStatusIndicator.jsx`
```jsx
/**
 * Progress bar and status for test execution
 */
<TestStatusIndicator
  current="test_create_chart"
  completed={3}
  total={10}
  status="running"
/>
```

#### 4. `TestResultPanel.jsx`
```jsx
/**
 * Collapsible test result with full details
 */
<TestResultPanel
  result={testResult}
  expanded={false}
  onToggle={() => {}}
/>
```

---

## Metrics to Track

### Space Efficiency
- **Current**: ~35% of screen is chrome (header/sidebar/input)
- **Target**: ~20% chrome, 80% content

### Chat UX
- **Current**: Variable message width causes layout shifts
- **Target**: Stable layout, no content-driven width

### Schema Readability
- **Current**: Raw JSON requires mental parsing
- **Target**: Visual types, clear hierarchy, expandable

### Test Feedback
- **Current**: Text-only status, console dependency
- **Target**: Visual progress, inline markers, live logs

---

## Technical Considerations

### Performance
- Schema rendering: Use `React.memo` for ParameterCard
- Test results: Virtualize if >50 tests
- Editor decorations: Debounce updates

### Accessibility
- All interactive elements keyboard navigable
- Progress indicators have aria-live regions
- Color is not sole indicator (use icons + text)

### Responsive Design
- Sidebar collapses to icons on narrow screens
- Chat messages stack properly on mobile
- Test runner switches to tabbed view on small screens

---

## Design Inspiration Sources

Since we can't access the agor repository, here are modern UI patterns to consider:

### Chat Interfaces
- **Linear**: Fixed-width messages, compact metadata
- **Vercel v0**: Auto-expanding input, inline code blocks
- **ChatGPT**: Clean message bubbles, subtle metadata

### Schema Viewers
- **Postman**: Visual parameter cards with type indicators
- **Swagger UI**: Collapsible schemas with examples
- **GraphiQL**: Tree-style type explorer

### Test Runners
- **VS Code Testing**: Inline gutter markers, tree view
- **Vitest UI**: Live progress, split results panel
- **Jest Runner**: Status icons, expandable failures

---

## Next Steps

1. **Review this plan** with team
2. **Create Figma mockups** for key changes (optional)
3. **Start with Phase 1** (space optimization)
4. **Iterate based on feedback**
5. **Add to README** once stabilized

---

## Open Questions

1. Should sidebar be collapsible on mobile?
2. Do we want keyboard shortcuts for navigation?
3. Should test results persist between runs?
4. Do we need dark/light theme toggle?
5. Should we add test filtering/search?

---

## References

- Current codebase: `/Users/amin/github/preset-io/testmcpy/testmcpy/ui/src/`
- Tailwind config: `/Users/amin/github/preset-io/testmcpy/testmcpy/ui/tailwind.config.js`
- Design tokens: `/Users/amin/github/preset-io/testmcpy/testmcpy/ui/src/index.css`
