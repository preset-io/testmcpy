import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import {
  Lock,
  Play,
  CheckCircle,
  XCircle,
  Clock,
  Download,
  Server,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  AlertCircle,
  Key,
  Shield,
  RefreshCw,
  HelpCircle,
  Loader,
  ArrowRight,
  Info,
  Eye,
  Timer
} from 'lucide-react'
import ReactJson from '@microlink/react-json-view'
import { useEditorTheme } from '../hooks/useEditorTheme'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

// Educational tooltips for each OAuth step
const OAUTH_STEP_EXPLANATIONS = {
  'Prepare OAuth Request': {
    title: 'Preparing OAuth Request',
    description: 'Building the authentication request with your client credentials. This step validates that all required parameters (client_id, client_secret, token_url) are present.',
    expected: 'Should complete instantly with no errors',
    icon: Lock
  },
  'Request Access Token': {
    title: 'Requesting Access Token',
    description: 'Making a POST request to the authorization server to exchange credentials for an access token. This uses client_credentials grant type.',
    expected: 'May receive 401 on first attempt - this is normal! The server might need to warm up or validate credentials.',
    icon: Server
  },
  'Parse Token Response': {
    title: 'Parsing Token Response',
    description: 'Extracting the access token from the server response. The response typically includes: access_token, token_type, expires_in, and optional scope.',
    expected: 'Should extract a valid JWT or opaque token string',
    icon: Key
  },
  'Validate Token': {
    title: 'Validating Token',
    description: 'Verifying the token format and basic structure. For JWT tokens, this checks signature and claims. For opaque tokens, this validates format.',
    expected: 'Token should be well-formed and not expired',
    icon: Shield
  }
}

// Actor swimlane node with vertical lifeline
function ActorNode({ data }) {
  const { label, color, active, isStart, isEnd, actorHeight } = data

  return (
    <div className="relative flex flex-col items-center" style={{ height: actorHeight }}>
      {/* Top label */}
      <div
        className={`px-4 py-2 rounded-lg border-2 shadow-lg transition-all duration-300 ${
          active
            ? `${color} border-white text-white shadow-2xl scale-110`
            : `bg-surface border-${color.replace('bg-', 'border-')}`
        }`}
        style={{
          minWidth: '140px',
          textAlign: 'center',
        }}
      >
        <div className={`text-xs font-bold ${active ? 'text-white' : 'text-text-primary'}`}>
          {label}
        </div>
      </div>

      {/* Vertical lifeline */}
      <div
        className={`flex-1 w-0.5 transition-all duration-800 ${
          active ? `${color.replace('bg-', 'bg-')} animate-pulse` : 'bg-border'
        }`}
        style={{
          marginTop: '8px',
          marginBottom: '8px',
        }}
      />

      {/* Bottom label (for symmetry) */}
      <div
        className={`px-4 py-2 rounded-lg border-2 transition-all duration-300 ${
          active
            ? `${color} border-white text-white shadow-lg`
            : `bg-surface border-${color.replace('bg-', 'border-')}`
        }`}
        style={{
          minWidth: '140px',
          textAlign: 'center',
        }}
      >
        <div className={`text-xs font-bold ${active ? 'text-white' : 'text-text-primary'}`}>
          {label}
        </div>
      </div>
    </div>
  )
}

// OAuth Sequence Diagram with beautiful swimlanes
function OAuthSequenceDiagram({ steps = [], currentStep = -1 }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [reactFlowInstance, setReactFlowInstance] = useState(null)
  const [selectedAction, setSelectedAction] = useState(null)

  // Actor positions (horizontal)
  const ACTOR_X_POSITIONS = {
    client: 150,
    mcpServer: 450,
    authServer: 750,
  }

  // Calculate diagram dimensions
  const ACTION_SPACING = 100
  const TOP_MARGIN = 80
  const BOTTOM_MARGIN = 80
  const totalActions = 6 // Total number of OAuth flow actions
  const actorHeight = TOP_MARGIN + (totalActions * ACTION_SPACING) + BOTTOM_MARGIN

  // Map step names to actions for OAuth flow
  const getActionStatus = (actionIndex) => {
    if (currentStep < 0) return 'pending'
    if (actionIndex === currentStep) return 'current'
    if (actionIndex < currentStep) return 'complete'
    return 'pending'
  }

  // Determine if there are errors from steps
  const hasError = steps.some(step => !step.success)

  // Build nodes and edges
  useEffect(() => {
    // Create actor swimlane nodes
    const actorNodes = [
      {
        id: 'client',
        type: 'actor',
        position: { x: ACTOR_X_POSITIONS.client, y: 0 },
        data: {
          label: 'Client\n(Your App)',
          color: 'bg-green-500',
          active: [0, 4].includes(currentStep),
          actorHeight: actorHeight,
        },
      },
      {
        id: 'mcpServer',
        type: 'actor',
        position: { x: ACTOR_X_POSITIONS.mcpServer, y: 0 },
        data: {
          label: 'MCP\nServer',
          color: 'bg-orange-500',
          active: [1, 5].includes(currentStep),
          actorHeight: actorHeight,
        },
      },
      {
        id: 'authServer',
        type: 'actor',
        position: { x: ACTOR_X_POSITIONS.authServer, y: 0 },
        data: {
          label: 'Auth\nServer',
          color: 'bg-blue-500',
          active: [2, 3].includes(currentStep),
          actorHeight: actorHeight,
        },
      },
    ]

    // Create action edges (arrows between actors)
    const flowEdges = [
      // Step 0: Client → MCP Server - Initial request
      {
        id: 'action-0',
        source: 'client',
        target: 'mcpServer',
        label: 'Initial MCP Request',
        animated: currentStep === 0,
        style: {
          strokeWidth: getActionStatus(0) === 'current' ? 3 : 2,
          stroke: getActionStatus(0) === 'complete' ? '#10b981' :
                  getActionStatus(0) === 'current' ? '#3b82f6' : '#6b7280',
          strokeDasharray: getActionStatus(0) === 'pending' ? '5,5' : '0',
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: getActionStatus(0) === 'complete' ? '#10b981' :
                 getActionStatus(0) === 'current' ? '#3b82f6' : '#6b7280',
        },
        data: {
          label: 'Initial MCP Request',
          status: getActionStatus(0),
          stepIndex: 0,
        },
      },
      // Step 1: MCP Server → Client - 401 + OAuth metadata
      {
        id: 'action-1',
        source: 'mcpServer',
        target: 'client',
        label: '401 + OAuth Metadata',
        animated: currentStep === 1,
        style: {
          strokeWidth: getActionStatus(1) === 'current' ? 3 : 2,
          stroke: getActionStatus(1) === 'complete' ? '#10b981' :
                  getActionStatus(1) === 'current' ? '#3b82f6' : '#6b7280',
          strokeDasharray: getActionStatus(1) === 'pending' ? '5,5' : '0',
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: getActionStatus(1) === 'complete' ? '#10b981' :
                 getActionStatus(1) === 'current' ? '#3b82f6' : '#6b7280',
        },
        data: {
          label: '401 + OAuth Metadata',
          status: getActionStatus(1),
          stepIndex: 1,
        },
      },
      // Step 2: Client → Auth Server - Request access token
      {
        id: 'action-2',
        source: 'client',
        target: 'authServer',
        label: 'Request Access Token',
        animated: currentStep === 2,
        style: {
          strokeWidth: getActionStatus(2) === 'current' ? 3 : 2,
          stroke: getActionStatus(2) === 'complete' ? '#10b981' :
                  getActionStatus(2) === 'current' ? '#3b82f6' : '#6b7280',
          strokeDasharray: getActionStatus(2) === 'pending' ? '5,5' : '0',
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: getActionStatus(2) === 'complete' ? '#10b981' :
                 getActionStatus(2) === 'current' ? '#3b82f6' : '#6b7280',
        },
        data: {
          label: 'Request Access Token',
          status: getActionStatus(2),
          stepIndex: 2,
        },
      },
      // Step 3: Auth Server → Client - Access token response
      {
        id: 'action-3',
        source: 'authServer',
        target: 'client',
        label: 'Access Token Response',
        animated: currentStep === 3,
        style: {
          strokeWidth: getActionStatus(3) === 'current' ? 3 : 2,
          stroke: getActionStatus(3) === 'complete' ? '#10b981' :
                  getActionStatus(3) === 'current' ? '#3b82f6' : '#6b7280',
          strokeDasharray: getActionStatus(3) === 'pending' ? '5,5' : '0',
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: getActionStatus(3) === 'complete' ? '#10b981' :
                 getActionStatus(3) === 'current' ? '#3b82f6' : '#6b7280',
        },
        data: {
          label: 'Access Token Response',
          status: getActionStatus(3),
          stepIndex: 3,
        },
      },
      // Step 4: Client → MCP Server - Authenticated request
      {
        id: 'action-4',
        source: 'client',
        target: 'mcpServer',
        label: 'Authenticated Request',
        animated: currentStep === 4,
        style: {
          strokeWidth: getActionStatus(4) === 'current' ? 3 : 2,
          stroke: getActionStatus(4) === 'complete' ? '#10b981' :
                  getActionStatus(4) === 'current' ? '#3b82f6' : '#6b7280',
          strokeDasharray: getActionStatus(4) === 'pending' ? '5,5' : '0',
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: getActionStatus(4) === 'complete' ? '#10b981' :
                 getActionStatus(4) === 'current' ? '#3b82f6' : '#6b7280',
        },
        data: {
          label: 'Authenticated Request',
          status: getActionStatus(4),
          stepIndex: 4,
        },
      },
      // Step 5: MCP Server → Client - Success response
      {
        id: 'action-5',
        source: 'mcpServer',
        target: 'client',
        label: 'Success Response',
        animated: currentStep === 5,
        style: {
          strokeWidth: getActionStatus(5) === 'current' ? 3 : 2,
          stroke: getActionStatus(5) === 'complete' ? '#10b981' :
                  getActionStatus(5) === 'current' ? '#3b82f6' : '#6b7280',
          strokeDasharray: getActionStatus(5) === 'pending' ? '5,5' : '0',
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: getActionStatus(5) === 'complete' ? '#10b981' :
                 getActionStatus(5) === 'current' ? '#3b82f6' : '#6b7280',
        },
        data: {
          label: 'Success Response',
          status: getActionStatus(5),
          stepIndex: 5,
        },
      },
    ]

    setNodes(actorNodes)
    setEdges(flowEdges)

    // Auto-zoom to current step with smooth animation
    if (reactFlowInstance && currentStep >= 0 && currentStep < 6) {
      setTimeout(() => {
        const actionY = TOP_MARGIN + (currentStep * ACTION_SPACING) + 50
        reactFlowInstance.setCenter(450, actionY, { duration: 800, zoom: 0.85 })
      }, 100)
    }
  }, [steps, currentStep, reactFlowInstance, actorHeight])

  const nodeTypes = useMemo(() => ({
    actor: ActorNode,
  }), [])

  return (
    <div className="relative min-h-[300px] md:min-h-[400px] h-[600px] bg-gradient-to-br from-surface to-surface-elevated rounded-lg border border-border overflow-hidden shadow-xl">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onInit={setReactFlowInstance}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 0.9 }}
        minZoom={0.3}
        maxZoom={1.5}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={true}
        onEdgeClick={(event, edge) => setSelectedAction(edge.data)}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          color="#374151"
          gap={16}
          size={0.5}
          variant="dots"
        />
        <Controls showInteractive={false} />
      </ReactFlow>

      {/* Legend */}
      <div className="absolute top-4 right-4 bg-surface-elevated/90 backdrop-blur-sm border border-border rounded-lg p-3 shadow-lg">
        <div className="text-xs font-semibold text-text-primary mb-2">Flow Status</div>
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <div className="w-4 h-0.5 bg-text-tertiary opacity-30" style={{ borderTop: '1.5px dashed' }}></div>
            <span className="text-xs text-text-secondary">Pending</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-0.5 bg-blue-500"></div>
            <span className="text-xs text-text-secondary">In Progress</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-0.5 bg-green-500"></div>
            <span className="text-xs text-text-secondary">Complete</span>
          </div>
        </div>
      </div>

      {/* Selected action details */}
      {selectedAction && (
        <div className="absolute bottom-4 left-4 right-4 bg-surface-elevated/95 backdrop-blur-sm border-2 border-primary rounded-lg p-4 shadow-2xl animate-fade-in-up">
          <div className="flex items-start justify-between mb-2">
            <h4 className="text-sm font-semibold text-text-primary">
              Step {selectedAction.stepIndex + 1}: {selectedAction.label}
            </h4>
            <button
              onClick={() => setSelectedAction(null)}
              className="text-text-tertiary hover:text-text-primary transition-colors"
            >
              <XCircle size={16} />
            </button>
          </div>
          <p className="text-xs text-text-secondary">
            {selectedAction.status === 'complete' && 'This step completed successfully.'}
            {selectedAction.status === 'current' && 'This step is currently in progress.'}
            {selectedAction.status === 'pending' && 'This step has not started yet.'}
            {selectedAction.status === 'error' && 'This step encountered an error.'}
          </p>
        </div>
      )}
    </div>
  )
}

// Educational Tooltip Component
function StepExplanation({ stepName, visible, onClose }) {
  const explanation = OAUTH_STEP_EXPLANATIONS[stepName]

  if (!visible || !explanation) return null

  const Icon = explanation.icon

  return (
    <div className="mt-2 p-4 bg-primary/5 border border-primary/30 rounded-lg">
      <div className="flex items-start gap-3">
        <Icon className="text-primary mt-1" size={20} />
        <div className="flex-1">
          <h4 className="font-semibold text-text-primary mb-1 flex items-center gap-2">
            {explanation.title}
            <button onClick={onClose} className="ml-auto text-text-tertiary hover:text-text-primary">
              <XCircle size={16} />
            </button>
          </h4>
          <p className="text-sm text-text-secondary mb-2">
            {explanation.description}
          </p>
          <div className="flex items-start gap-2 mt-2 p-2 bg-surface rounded">
            <Info size={14} className="text-primary mt-0.5" />
            <p className="text-xs text-text-tertiary">
              <strong>Expected:</strong> {explanation.expected}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

// JWT Token Decoder Component
function JWTDecoder({ jsonTheme }) {
  const [tokenInput, setTokenInput] = useState('')
  const [decoded, setDecoded] = useState(null)
  const [decodeError, setDecodeError] = useState(null)

  const decodeToken = () => {
    setDecoded(null)
    setDecodeError(null)

    if (!tokenInput.trim()) {
      setDecodeError('Please paste a JWT token')
      return
    }

    try {
      const parts = tokenInput.trim().split('.')
      if (parts.length !== 3) {
        setDecodeError(`Invalid JWT structure: expected 3 parts, got ${parts.length}`)
        return
      }

      // Decode header
      const headerJson = atob(parts[0].replace(/-/g, '+').replace(/_/g, '/'))
      const header = JSON.parse(headerJson)

      // Decode payload
      let payloadB64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
      while (payloadB64.length % 4) payloadB64 += '='
      const payloadJson = atob(payloadB64)
      const payload = JSON.parse(payloadJson)

      setDecoded({ header, payload, signature: parts[2].substring(0, 20) + '...' })
    } catch (e) {
      setDecodeError(`Failed to decode: ${e.message}`)
    }
  }

  return (
    <div className="bg-surface-elevated rounded-xl border border-border p-6 space-y-4">
      <h3 className="text-lg font-semibold text-text-primary flex items-center gap-2">
        <Eye size={20} className="text-primary" />
        JWT Token Decoder
      </h3>
      <div>
        <textarea
          value={tokenInput}
          onChange={(e) => setTokenInput(e.target.value)}
          placeholder="Paste a JWT token here (eyJhbG...)"
          rows={3}
          className="w-full px-3 py-2 bg-surface border border-border rounded-lg text-text-primary placeholder-text-disabled focus:outline-none focus:ring-2 focus:ring-primary font-mono text-sm"
        />
        <button
          onClick={decodeToken}
          className="mt-2 px-4 py-2 bg-primary hover:bg-primary/90 text-white rounded-lg transition-colors flex items-center gap-2 text-sm"
        >
          <Key size={16} />
          Decode Token
        </button>
      </div>

      {decodeError && (
        <div className="p-3 bg-error/10 border border-error/30 rounded-lg text-sm text-error">
          {decodeError}
        </div>
      )}

      {decoded && (
        <div className="space-y-3">
          <div>
            <div className="text-xs font-semibold text-text-secondary mb-1">Header</div>
            <div className="bg-background-subtle rounded-lg p-3 border border-border">
              <ReactJson
                src={decoded.header}
                theme={jsonTheme}
                collapsed={false}
                displayDataTypes={false}
                name="header"
                indentWidth={2}
                style={{ backgroundColor: 'transparent', fontSize: '12px', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}
              />
            </div>
          </div>
          <div>
            <div className="text-xs font-semibold text-text-secondary mb-1">Payload</div>
            <div className="bg-background-subtle rounded-lg p-3 border border-border">
              <ReactJson
                src={decoded.payload}
                theme={jsonTheme}
                collapsed={false}
                displayDataTypes={false}
                name="payload"
                indentWidth={2}
                style={{ backgroundColor: 'transparent', fontSize: '12px', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}
              />
            </div>
          </div>

          {/* Expiry Countdown */}
          {decoded.payload.exp && (
            <ExpiryCountdown exp={decoded.payload.exp} />
          )}

          <div className="text-xs text-text-tertiary">
            Signature: <span className="font-mono">{decoded.signature}</span>
          </div>
        </div>
      )}
    </div>
  )
}

// Live Expiry Countdown Component
function ExpiryCountdown({ exp }) {
  const [timeLeft, setTimeLeft] = useState(null)
  const intervalRef = useRef(null)

  useEffect(() => {
    const update = () => {
      const now = Math.floor(Date.now() / 1000)
      const remaining = exp - now
      setTimeLeft(remaining)
    }

    update()
    intervalRef.current = setInterval(update, 1000)
    return () => clearInterval(intervalRef.current)
  }, [exp])

  if (timeLeft === null) return null

  const isExpired = timeLeft <= 0
  const absTime = Math.abs(timeLeft)
  const hours = Math.floor(absTime / 3600)
  const minutes = Math.floor((absTime % 3600) / 60)
  const seconds = absTime % 60

  const formatted = hours > 0
    ? `${hours}h ${minutes}m ${seconds}s`
    : minutes > 0
      ? `${minutes}m ${seconds}s`
      : `${seconds}s`

  return (
    <div className={`flex items-center gap-2 p-3 rounded-lg border ${
      isExpired
        ? 'bg-error/10 border-error/30'
        : timeLeft < 300
          ? 'bg-yellow-500/10 border-yellow-500/30'
          : 'bg-success/10 border-success/30'
    }`}>
      <Timer size={16} className={isExpired ? 'text-error' : timeLeft < 300 ? 'text-yellow-500' : 'text-success'} />
      <div>
        <div className={`text-sm font-medium ${isExpired ? 'text-error' : timeLeft < 300 ? 'text-yellow-500' : 'text-success'}`}>
          {isExpired ? `Expired ${formatted} ago` : `Expires in ${formatted}`}
        </div>
        <div className="text-xs text-text-tertiary">
          {new Date(exp * 1000).toLocaleString()}
        </div>
      </div>
    </div>
  )
}

// Test Refresh Button Component
function TestRefreshButton({ tokenUrl, refreshToken, clientId, clientSecret, onNewToken }) {
  const [refreshing, setRefreshing] = useState(false)
  const [refreshResult, setRefreshResult] = useState(null)

  const handleTestRefresh = async () => {
    if (!tokenUrl || !refreshToken) return

    setRefreshing(true)
    setRefreshResult(null)

    try {
      const res = await fetch('/api/debug-auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          auth_type: 'oauth',
          token_url: tokenUrl,
          client_id: clientId,
          client_secret: clientSecret,
          refresh_token: refreshToken,
        })
      })
      const data = await res.json()

      if (data.success) {
        const tokenStep = data.steps.find(s => s.step.includes('Token Extracted'))
        const newToken = tokenStep?.data?.access_token
        setRefreshResult({ success: true, token_preview: newToken ? newToken.substring(0, 30) + '...' : 'token obtained' })
        if (newToken && onNewToken) onNewToken(newToken)
      } else {
        setRefreshResult({ success: false, error: data.error || 'Refresh failed' })
      }
    } catch (e) {
      setRefreshResult({ success: false, error: e.message })
    } finally {
      setRefreshing(false)
    }
  }

  if (!tokenUrl || !refreshToken) return null

  return (
    <div className="space-y-2">
      <button
        onClick={handleTestRefresh}
        disabled={refreshing}
        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors flex items-center gap-2 text-sm disabled:opacity-50"
      >
        {refreshing ? (
          <>
            <Loader className="animate-spin" size={16} />
            Refreshing...
          </>
        ) : (
          <>
            <RefreshCw size={16} />
            Test Token Refresh
          </>
        )}
      </button>

      {refreshResult && (
        <div className={`p-3 rounded-lg border text-sm ${
          refreshResult.success
            ? 'bg-success/10 border-success/30 text-success'
            : 'bg-error/10 border-error/30 text-error'
        }`}>
          {refreshResult.success
            ? `Token refreshed: ${refreshResult.token_preview}`
            : `Refresh failed: ${refreshResult.error}`
          }
        </div>
      )}
    </div>
  )
}

function AuthDebugger() {
  const { jsonTheme } = useEditorTheme()
  const [authType, setAuthType] = useState('oauth')
  const [profiles, setProfiles] = useState([])
  const [selectedProfile, setSelectedProfile] = useState('')
  const [loading, setLoading] = useState(false)
  const [debugResult, setDebugResult] = useState(null)
  const [expandedSteps, setExpandedSteps] = useState(new Set())
  const [copiedStep, setCopiedStep] = useState(null)
  const [currentStep, setCurrentStep] = useState(-1)
  const [showExplanation, setShowExplanation] = useState(null)
  const [isRetrying, setIsRetrying] = useState(false)
  const [authError, setAuthError] = useState(null)
  const [progressMessage, setProgressMessage] = useState('')

  // Form fields for OAuth
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [tokenUrl, setTokenUrl] = useState('')
  const [scopes, setScopes] = useState('')
  const [oauthAutoDiscover, setOauthAutoDiscover] = useState(false)
  const [insecure, setInsecure] = useState(false)

  // Form fields for JWT
  const [apiUrl, setApiUrl] = useState('')
  const [apiToken, setApiToken] = useState('')
  const [apiSecret, setApiSecret] = useState('')

  // Form fields for Bearer
  const [bearerToken, setBearerToken] = useState('')
  const [mcpUrl, setMcpUrl] = useState('')

  useEffect(() => {
    loadProfiles()
  }, [])

  const loadProfiles = async () => {
    try {
      const res = await fetch('/api/mcp/profiles')
      const data = await res.json()
      setProfiles(data.profiles || [])
    } catch (error) {
      console.error('Failed to load profiles:', error)
    }
  }

  const loadFromProfile = async (profileId) => {
    if (!profileId) {
      clearForm()
      return
    }

    try {
      // Fetch unmasked auth config
      const res = await fetch(`/api/mcp/profiles/${profileId}/auth`)
      if (!res.ok) {
        console.error('Failed to load profile auth')
        return
      }
      const auth = await res.json()

      const type = auth.type?.toLowerCase() || 'oauth'
      setAuthType(type)
      setMcpUrl(auth.mcp_url || '')

      if (type === 'oauth') {
        setClientId(auth.client_id || '')
        setClientSecret(auth.client_secret || '')
        setTokenUrl(auth.token_url || '')
        setScopes((auth.scopes || []).join(', '))
        setOauthAutoDiscover(auth.oauth_auto_discover || false)
        setInsecure(auth.insecure || false)
      } else if (type === 'jwt') {
        setApiUrl(auth.api_url || '')
        setApiToken(auth.api_token || '')
        setApiSecret(auth.api_secret || '')
      } else if (type === 'bearer') {
        setBearerToken(auth.token || '')
      }
    } catch (error) {
      console.error('Failed to load profile auth:', error)
    }
  }

  const clearForm = () => {
    setClientId('')
    setClientSecret('')
    setTokenUrl('')
    setScopes('')
    setOauthAutoDiscover(false)
    setInsecure(false)
    setApiUrl('')
    setApiToken('')
    setApiSecret('')
    setBearerToken('')
    setMcpUrl('')
    setDebugResult(null)
  }

  const handleProfileChange = (profileId) => {
    setSelectedProfile(profileId)
    loadFromProfile(profileId)
  }

  const handleDebugAuth = async (isRetry = false) => {
    setLoading(true)
    setDebugResult(null)
    setExpandedSteps(new Set())
    setCurrentStep(-1)
    setAuthError(null)
    setProgressMessage('Initializing authentication flow...')

    if (isRetry) {
      setIsRetrying(true)
    }

    try {
      let requestBody = { auth_type: authType }

      if (authType === 'oauth') {
        requestBody = {
          ...requestBody,
          client_id: clientId,
          client_secret: clientSecret,
          token_url: tokenUrl,
          scopes: scopes ? scopes.split(',').map(s => s.trim()) : [],
          oauth_auto_discover: oauthAutoDiscover,
          insecure: insecure,
          mcp_url: mcpUrl
        }
      } else if (authType === 'jwt') {
        requestBody = {
          ...requestBody,
          api_url: apiUrl,
          api_token: apiToken,
          api_secret: apiSecret
        }
      } else if (authType === 'bearer') {
        requestBody = {
          ...requestBody,
          token: bearerToken,
          mcp_url: mcpUrl
        }
      }

      setProgressMessage('Sending authentication request...')
      setCurrentStep(0)

      const res = await fetch('/api/debug-auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      })

      setProgressMessage('Processing authentication response...')
      setCurrentStep(1)

      const data = await res.json()

      setProgressMessage('Validating token...')
      setCurrentStep(2)

      // Simulate step progression for better UX
      await new Promise(resolve => setTimeout(resolve, 500))

      setProgressMessage('Authentication complete!')
      setCurrentStep(3)

      setDebugResult(data)

      // Auto-expand all steps
      setExpandedSteps(new Set(data.steps.map((_, i) => i)))

      // For JWT/OAuth success, populate bearer token field with the obtained token
      if (data.success && (authType === 'jwt' || authType === 'oauth')) {
        // Find access_token from the "Token Extracted" step
        const tokenStep = data.steps.find(s => s.step.includes('Token Extracted'))
        if (tokenStep?.data?.access_token) {
          setBearerToken(tokenStep.data.access_token)
        }
      }

      if (!data.success) {
        setAuthError(data.error)
      }
    } catch (error) {
      console.error('Failed to debug auth:', error)
      const errorMessage = error.message || 'Failed to debug authentication'
      setAuthError(errorMessage)
      setDebugResult({
        success: false,
        error: errorMessage,
        steps: [],
        total_time: 0,
        auth_type: authType
      })
    } finally {
      setLoading(false)
      setIsRetrying(false)
      setProgressMessage('')
      // Reset to final step after completion
      setTimeout(() => setCurrentStep(3), 500)
    }
  }

  const handleRetry = () => {
    handleDebugAuth(true)
  }

  const handleDebugProfileAuth = async () => {
    if (!selectedProfile) return

    setLoading(true)
    setDebugResult(null)
    setExpandedSteps(new Set())
    setCurrentStep(-1)
    setAuthError(null)
    setProgressMessage('Loading profile configuration...')

    try {
      setProgressMessage('Authenticating with profile...')
      setCurrentStep(0)

      const res = await fetch(`/api/mcp/profiles/${selectedProfile}/debug-auth`, {
        method: 'POST'
      })

      setProgressMessage('Processing authentication...')
      setCurrentStep(1)

      const data = await res.json()

      setProgressMessage('Validating credentials...')
      setCurrentStep(2)

      await new Promise(resolve => setTimeout(resolve, 500))

      setProgressMessage('Profile authentication complete!')
      setCurrentStep(3)

      setDebugResult(data)

      // Auto-expand all steps
      setExpandedSteps(new Set(data.steps.map((_, i) => i)))

      // For JWT/OAuth success, populate bearer token field with the obtained token
      if (data.success) {
        const tokenStep = data.steps.find(s => s.step.includes('Token Extracted'))
        if (tokenStep?.data?.access_token) {
          setBearerToken(tokenStep.data.access_token)
        }
      }

      if (!data.success) {
        setAuthError(data.error)
      }
    } catch (error) {
      console.error('Failed to debug profile auth:', error)
      const errorMessage = error.message || 'Failed to debug profile authentication'
      setAuthError(errorMessage)
      setDebugResult({
        success: false,
        error: errorMessage,
        steps: [],
        total_time: 0
      })
    } finally {
      setLoading(false)
      setProgressMessage('')
      setTimeout(() => setCurrentStep(3), 500)
    }
  }

  const toggleStep = (index) => {
    const newExpanded = new Set(expandedSteps)
    if (newExpanded.has(index)) {
      newExpanded.delete(index)
    } else {
      newExpanded.add(index)
    }
    setExpandedSteps(newExpanded)
  }

  const exportTrace = () => {
    if (!debugResult) return

    const trace = {
      timestamp: new Date().toISOString(),
      auth_type: debugResult.auth_type,
      success: debugResult.success,
      total_time: debugResult.total_time,
      steps: debugResult.steps,
      error: debugResult.error
    }

    const blob = new Blob([JSON.stringify(trace, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `auth-trace-${debugResult.auth_type}-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const copyStepData = (stepIndex) => {
    if (!debugResult || !debugResult.steps[stepIndex]) return

    const step = debugResult.steps[stepIndex]
    navigator.clipboard.writeText(JSON.stringify(step.data, null, 2))
    setCopiedStep(stepIndex)
    setTimeout(() => setCopiedStep(null), 2000)
  }

  const canDebug = () => {
    if (authType === 'oauth') {
      // Auto-discover mode only needs mcp_url
      if (oauthAutoDiscover) {
        return mcpUrl
      }
      return clientId && clientSecret && tokenUrl
    } else if (authType === 'jwt') {
      return apiUrl && apiToken && apiSecret
    } else if (authType === 'bearer') {
      return bearerToken && mcpUrl
    }
    return false
  }

  return (
    <div className="h-full overflow-auto bg-background">
      <div className="max-w-7xl mx-auto p-4 md:p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl md:text-2xl font-bold text-text-primary flex items-center gap-3">
              <div className="p-2 bg-primary/10 rounded-lg">
                <Shield className="text-primary" size={28} />
              </div>
              Auth Debugger
            </h1>
            <p className="text-text-secondary mt-2">
              Debug OAuth, JWT, and Bearer token authentication flows with detailed step-by-step traces
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Configuration Panel */}
          <div className="space-y-4">
            <div className="bg-surface-elevated rounded-xl border border-border p-6 space-y-4">
              <h2 className="text-lg font-semibold text-text-primary flex items-center gap-2">
                <Lock size={20} className="text-primary" />
                Configuration
              </h2>

              {/* Load from Profile */}
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">
                  Load from MCP Profile (Optional)
                </label>
                <div className="flex gap-2">
                  <select
                    value={selectedProfile}
                    onChange={(e) => handleProfileChange(e.target.value)}
                    className="flex-1 px-3 py-2 bg-surface border border-border rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <option value="">Select a profile...</option>
                    {profiles.map(profile => (
                      <option key={profile.id} value={profile.id}>
                        {profile.name}
                      </option>
                    ))}
                  </select>
                  {selectedProfile && (
                    <button
                      onClick={handleDebugProfileAuth}
                      disabled={loading}
                      className="px-4 py-2 bg-success hover:bg-success/90 text-white rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50"
                    >
                      <Play size={16} />
                      Debug Profile
                    </button>
                  )}
                </div>
              </div>

              <div className="border-t border-border pt-4">
                <p className="text-xs text-text-tertiary mb-4">Or configure authentication manually:</p>

                {/* Auth Type Selector */}
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-2">
                    Authentication Type
                  </label>
                  <div className="flex gap-2">
                    {['oauth', 'jwt', 'bearer'].map(type => (
                      <button
                        key={type}
                        onClick={() => setAuthType(type)}
                        className={`flex-1 px-4 py-2 rounded-lg font-medium transition-colors ${
                          authType === type
                            ? 'bg-primary text-white'
                            : 'bg-surface border border-border text-text-secondary hover:text-text-primary'
                        }`}
                      >
                        {type.toUpperCase()}
                      </button>
                    ))}
                  </div>
                </div>

                {/* OAuth Fields */}
                {authType === 'oauth' && (
                  <div className="space-y-3 mt-4">
                    {/* Auto-discover checkbox */}
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        id="oauth-auto-discover"
                        checked={oauthAutoDiscover}
                        onChange={(e) => setOauthAutoDiscover(e.target.checked)}
                        className="w-4 h-4 rounded border-border bg-surface text-primary focus:ring-primary"
                      />
                      <label htmlFor="oauth-auto-discover" className="text-sm text-text-secondary">
                        Use RFC 8414 Auto-Discovery
                      </label>
                    </div>

                    {/* MCP URL - shown when auto-discover is enabled */}
                    {oauthAutoDiscover && (
                      <div>
                        <label className="block text-sm font-medium text-text-secondary mb-1">
                          MCP URL
                        </label>
                        <input
                          type="text"
                          value={mcpUrl}
                          onChange={(e) => setMcpUrl(e.target.value)}
                          placeholder="https://localhost:5443/mcp"
                          className="w-full px-3 py-2 bg-surface border border-border rounded-lg text-text-primary placeholder-text-disabled focus:outline-none focus:ring-2 focus:ring-primary"
                        />
                        <p className="text-xs text-text-tertiary mt-1">
                          OAuth endpoints will be discovered from /.well-known/oauth-authorization-server
                        </p>
                      </div>
                    )}

                    {/* Manual OAuth fields - hidden when auto-discover is enabled */}
                    {!oauthAutoDiscover && (
                      <>
                        <div>
                          <label className="block text-sm font-medium text-text-secondary mb-1">
                            Client ID
                          </label>
                          <input
                            type="text"
                            value={clientId}
                            onChange={(e) => setClientId(e.target.value)}
                            placeholder="your-client-id"
                            className="w-full px-3 py-2 bg-surface border border-border rounded-lg text-text-primary placeholder-text-disabled focus:outline-none focus:ring-2 focus:ring-primary"
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-text-secondary mb-1">
                            Client Secret
                          </label>
                          <input
                            type="text"
                            value={clientSecret}
                            onChange={(e) => setClientSecret(e.target.value)}
                            placeholder="your-client-secret"
                            className="w-full px-3 py-2 bg-surface border border-border rounded-lg text-text-primary placeholder-text-disabled focus:outline-none focus:ring-2 focus:ring-primary font-mono text-sm"
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-text-secondary mb-1">
                            Token URL
                          </label>
                          <input
                            type="text"
                            value={tokenUrl}
                            onChange={(e) => setTokenUrl(e.target.value)}
                            placeholder="https://auth.example.com/oauth/token"
                            className="w-full px-3 py-2 bg-surface border border-border rounded-lg text-text-primary placeholder-text-disabled focus:outline-none focus:ring-2 focus:ring-primary"
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-text-secondary mb-1">
                            Scopes (comma-separated)
                          </label>
                          <input
                            type="text"
                            value={scopes}
                            onChange={(e) => setScopes(e.target.value)}
                            placeholder="read, write"
                            className="w-full px-3 py-2 bg-surface border border-border rounded-lg text-text-primary placeholder-text-disabled focus:outline-none focus:ring-2 focus:ring-primary"
                          />
                        </div>
                      </>
                    )}

                    {/* Insecure checkbox for self-signed certs */}
                    <div className="flex items-center gap-2 pt-2 border-t border-border">
                      <input
                        type="checkbox"
                        id="oauth-insecure"
                        checked={insecure}
                        onChange={(e) => setInsecure(e.target.checked)}
                        className="w-4 h-4 rounded border-border bg-surface text-primary focus:ring-primary"
                      />
                      <label htmlFor="oauth-insecure" className="text-sm text-text-secondary">
                        Skip SSL verification (for self-signed certs)
                      </label>
                    </div>
                  </div>
                )}

                {/* JWT Fields */}
                {authType === 'jwt' && (
                  <div className="space-y-3 mt-4">
                    <div>
                      <label className="block text-sm font-medium text-text-secondary mb-1">
                        API URL
                      </label>
                      <input
                        type="text"
                        value={apiUrl}
                        onChange={(e) => setApiUrl(e.target.value)}
                        placeholder="https://api.example.com/auth/token"
                        className="w-full px-3 py-2 bg-surface border border-border rounded-lg text-text-primary placeholder-text-disabled focus:outline-none focus:ring-2 focus:ring-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-text-secondary mb-1">
                        API Token
                      </label>
                      <input
                        type="text"
                        value={apiToken}
                        onChange={(e) => setApiToken(e.target.value)}
                        placeholder="your-api-token"
                        className="w-full px-3 py-2 bg-surface border border-border rounded-lg text-text-primary placeholder-text-disabled focus:outline-none focus:ring-2 focus:ring-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-text-secondary mb-1">
                        API Secret
                      </label>
                      <input
                        type="text"
                        value={apiSecret}
                        onChange={(e) => setApiSecret(e.target.value)}
                        placeholder="your-api-secret"
                        className="w-full px-3 py-2 bg-surface border border-border rounded-lg text-text-primary placeholder-text-disabled focus:outline-none focus:ring-2 focus:ring-primary font-mono text-sm"
                      />
                    </div>
                  </div>
                )}

                {/* Bearer Fields */}
                {authType === 'bearer' && (
                  <div className="space-y-3 mt-4">
                    <div>
                      <label className="block text-sm font-medium text-text-secondary mb-1">
                        MCP URL
                      </label>
                      <input
                        type="text"
                        value={mcpUrl}
                        onChange={(e) => setMcpUrl(e.target.value)}
                        placeholder="https://your-instance.example.com/mcp"
                        className="w-full px-3 py-2 bg-surface border border-border rounded-lg text-text-primary placeholder-text-disabled focus:outline-none focus:ring-2 focus:ring-primary"
                      />
                      <p className="text-xs text-text-tertiary mt-1">
                        Token will be tested by calling tools/list on this endpoint
                      </p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-text-secondary mb-1">
                        Bearer Token
                      </label>
                      <textarea
                        value={bearerToken}
                        onChange={(e) => setBearerToken(e.target.value)}
                        placeholder="your-bearer-token"
                        rows={4}
                        className="w-full px-3 py-2 bg-surface border border-border rounded-lg text-text-primary placeholder-text-disabled focus:outline-none focus:ring-2 focus:ring-primary font-mono text-sm"
                      />
                    </div>
                  </div>
                )}

                {/* Debug Button */}
                <button
                  onClick={handleDebugAuth}
                  disabled={loading || !canDebug()}
                  className="w-full mt-4 px-4 py-3 bg-primary hover:bg-primary/90 text-white rounded-lg transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                >
                  {loading ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                      Debugging...
                    </>
                  ) : (
                    <>
                      <Play size={18} />
                      Debug Auth Flow
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Results Panel */}
          <div className="space-y-4">
            {/* Loading State with Progress */}
            {loading && (
              <div className="bg-surface-elevated rounded-xl border border-border p-6">
                <div className="flex items-center gap-3 mb-4">
                  <Loader className="animate-spin text-primary" size={24} />
                  <div>
                    <h3 className="text-lg font-semibold text-text-primary">
                      {isRetrying ? 'Retrying Authentication...' : 'Authenticating...'}
                    </h3>
                    <p className="text-sm text-text-secondary mt-1">
                      {progressMessage}
                    </p>
                  </div>
                </div>

                {/* Progress Bar */}
                <div className="w-full bg-surface rounded-full h-2 mb-4">
                  <div
                    className="bg-primary h-2 rounded-full transition-all duration-500"
                    style={{ width: `${((currentStep + 1) / 4) * 100}%` }}
                  />
                </div>

                {/* Sequence Diagram During Loading */}
                {authType === 'oauth' && (
                  <div className="mt-4">
                    <h4 className="text-sm font-medium text-text-secondary mb-2">OAuth Flow Progress</h4>
                    <OAuthSequenceDiagram steps={[]} currentStep={currentStep} />
                  </div>
                )}
              </div>
            )}

            {debugResult && (
              <>
                {/* Sequence Diagram */}
                {authType === 'oauth' && (
                  <div className="bg-surface-elevated rounded-xl border border-border p-6">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-lg font-semibold text-text-primary flex items-center gap-2">
                        <ArrowRight className="text-primary" size={20} />
                        OAuth Flow Visualization
                      </h3>
                      <button
                        onClick={() => setShowExplanation(showExplanation ? null : 'overview')}
                        className="px-3 py-1 bg-primary/10 hover:bg-primary/20 text-primary rounded-lg transition-colors flex items-center gap-2 text-sm"
                      >
                        <HelpCircle size={16} />
                        {showExplanation ? 'Hide' : 'Show'} Guide
                      </button>
                    </div>
                    <OAuthSequenceDiagram steps={debugResult.steps} currentStep={debugResult.success ? 3 : currentStep} />

                    {showExplanation === 'overview' && (
                      <div className="mt-4 p-4 bg-primary/5 border border-primary/30 rounded-lg">
                        <h4 className="font-semibold text-text-primary mb-2 flex items-center gap-2">
                          <Info className="text-primary" size={18} />
                          Understanding OAuth Flow
                        </h4>
                        <p className="text-sm text-text-secondary mb-3">
                          OAuth 2.0 Client Credentials flow involves these key steps:
                        </p>
                        <ol className="text-sm text-text-secondary space-y-2 ml-4">
                          <li><strong className="text-green-500">1. Client Prepares:</strong> Your app gathers client_id, client_secret, and token_url</li>
                          <li><strong className="text-orange-500">2. Token Request:</strong> MCP server requests an access token from the auth server</li>
                          <li><strong className="text-blue-500">3. Token Response:</strong> Auth server validates credentials and returns a token</li>
                          <li><strong className="text-green-500">4. Token Validated:</strong> Token is parsed and ready for API calls</li>
                        </ol>
                        <div className="mt-3 p-2 bg-yellow-500/10 border border-yellow-500/30 rounded">
                          <p className="text-xs text-text-secondary">
                            <strong>Note:</strong> A 401 error on the first request is often normal - the auth server may need to warm up or validate credentials on first contact.
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Summary Card */}
                <div className={`bg-surface-elevated rounded-xl border-2 p-6 ${
                  debugResult.success
                    ? 'border-success/50 bg-success/5'
                    : 'border-error/50 bg-error/5'
                }`}>
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                      {debugResult.success ? (
                        <CheckCircle className="text-success" size={32} />
                      ) : (
                        <XCircle className="text-error" size={32} />
                      )}
                      <div>
                        <h3 className="text-lg font-semibold text-text-primary">
                          {debugResult.success ? 'Authentication Successful' : 'Authentication Failed'}
                        </h3>
                        <p className="text-sm text-text-secondary mt-1">
                          {debugResult.auth_type.toUpperCase()} Flow
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={exportTrace}
                      className="px-3 py-2 bg-surface hover:bg-surface-hover border border-border rounded-lg transition-colors flex items-center gap-2 text-sm"
                    >
                      <Download size={16} />
                      Export
                    </button>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="bg-surface rounded-lg p-3">
                      <div className="text-xs text-text-tertiary mb-1">Total Steps</div>
                      <div className="text-2xl font-bold text-text-primary">
                        {debugResult.steps.length}
                      </div>
                    </div>
                    <div className="bg-surface rounded-lg p-3">
                      <div className="text-xs text-text-tertiary mb-1">Duration</div>
                      <div className="text-2xl font-bold text-text-primary flex items-center gap-1">
                        <Clock size={20} />
                        {(debugResult.total_time * 1000).toFixed(0)}ms
                      </div>
                    </div>
                  </div>

                  {debugResult.token_preview && (
                    <div className="mt-4 p-3 bg-surface rounded-lg">
                      <div className="text-xs text-text-tertiary mb-2 flex items-center gap-2">
                        <Key size={14} />
                        Token Preview
                      </div>
                      <div className="font-mono text-xs text-text-primary break-all">
                        {debugResult.token_preview}
                      </div>
                    </div>
                  )}

                  {debugResult.error && (
                    <div className="mt-4 p-4 bg-error/10 border-2 border-error/30 rounded-lg">
                      <div className="flex items-start gap-3">
                        <AlertCircle size={20} className="mt-0.5 flex-shrink-0 text-error" />
                        <div className="flex-1">
                          <div className="font-semibold mb-2 text-error flex items-center gap-2">
                            Error Details
                            <span className="text-xs font-normal px-2 py-0.5 bg-error/20 rounded">
                              {debugResult.auth_type?.toUpperCase()}
                            </span>
                          </div>
                          <div className="text-sm text-error/90 mb-3 font-mono bg-surface-hover p-2 rounded">
                            {debugResult.error}
                          </div>

                          {/* Actionable error guidance */}
                          <div className="text-xs text-text-secondary mb-3 p-2 bg-surface rounded">
                            <strong>Common Solutions:</strong>
                            <ul className="mt-1 ml-4 list-disc space-y-1">
                              <li>Verify your credentials are correct</li>
                              <li>Check if the token URL is accessible</li>
                              <li>Ensure network connectivity to auth server</li>
                              <li>Try again - first request failures are sometimes normal</li>
                            </ul>
                          </div>

                          {/* Retry Button */}
                          <button
                            onClick={handleRetry}
                            disabled={isRetrying}
                            className="px-4 py-2 bg-error hover:bg-error/90 text-white rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {isRetrying ? (
                              <>
                                <Loader className="animate-spin" size={16} />
                                Retrying...
                              </>
                            ) : (
                              <>
                                <RefreshCw size={16} />
                                Retry Authentication
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Steps */}
                <div className="bg-surface-elevated rounded-xl border border-border p-6">
                  <h3 className="text-lg font-semibold text-text-primary mb-4">
                    Authentication Flow Steps
                  </h3>

                  <div className="space-y-2">
                    {debugResult.steps.map((step, index) => {
                      const isExpanded = expandedSteps.has(index)
                      const isSuccess = step.success
                      const hasExplanation = OAUTH_STEP_EXPLANATIONS[step.step]

                      return (
                        <div
                          key={index}
                          className={`border rounded-lg overflow-hidden transition-colors ${
                            isSuccess
                              ? 'border-success/30 bg-success/5'
                              : 'border-error/30 bg-error/5'
                          }`}
                        >
                          <button
                            onClick={() => toggleStep(index)}
                            className="w-full px-4 py-3 flex items-center justify-between hover:bg-surface/50 transition-colors"
                          >
                            <div className="flex items-center gap-3">
                              {isSuccess ? (
                                <CheckCircle className="text-success" size={20} />
                              ) : (
                                <XCircle className="text-error" size={20} />
                              )}
                              <div className="text-left">
                                <div className="font-medium text-text-primary flex items-center gap-2">
                                  {step.step}
                                  {hasExplanation && (
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        setShowExplanation(showExplanation === step.step ? null : step.step)
                                      }}
                                      className="p-1 hover:bg-primary/20 rounded transition-colors"
                                      title="Learn more about this step"
                                    >
                                      <HelpCircle className="text-primary" size={14} />
                                    </button>
                                  )}
                                </div>
                                <div className="text-xs text-text-tertiary mt-1">
                                  {(step.timestamp * 1000).toFixed(0)}ms
                                </div>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation()
                                  copyStepData(index)
                                }}
                                className="p-2 hover:bg-surface rounded transition-colors"
                                title="Copy step data"
                              >
                                {copiedStep === index ? (
                                  <Check className="text-success" size={16} />
                                ) : (
                                  <Copy className="text-text-tertiary" size={16} />
                                )}
                              </button>
                              {isExpanded ? (
                                <ChevronDown size={20} className="text-text-secondary" />
                              ) : (
                                <ChevronRight size={20} className="text-text-secondary" />
                              )}
                            </div>
                          </button>

                          {/* Educational Explanation */}
                          {showExplanation === step.step && (
                            <div className="px-4 pb-2">
                              <StepExplanation
                                stepName={step.step}
                                visible={true}
                                onClose={() => setShowExplanation(null)}
                              />
                            </div>
                          )}

                          {isExpanded && (
                            <div className="px-4 pb-4 space-y-3">
                              {/* Raw Request */}
                              {step.data.raw_request && (
                                <div>
                                  <div className="text-xs font-semibold text-text-secondary mb-1 flex items-center gap-2">
                                    <ArrowRight size={12} className="text-blue-400" />
                                    Raw Request
                                  </div>
                                  <pre className="bg-blue-950/50 rounded-lg p-3 border border-blue-500/30 text-xs font-mono text-blue-200 overflow-x-auto whitespace-pre-wrap">
                                    {step.data.raw_request}
                                  </pre>
                                </div>
                              )}

                              {/* Raw Response */}
                              {step.data.raw_response && (
                                <div>
                                  <div className="text-xs font-semibold text-text-secondary mb-1 flex items-center gap-2">
                                    <ArrowRight size={12} className="text-green-400 rotate-180" />
                                    Raw Response
                                  </div>
                                  <pre className="bg-green-950/50 rounded-lg p-3 border border-green-500/30 text-xs font-mono text-green-200 overflow-x-auto whitespace-pre-wrap max-h-64 overflow-y-auto">
                                    {step.data.raw_response}
                                  </pre>
                                </div>
                              )}

                              {/* Parsed Data */}
                              <div>
                                <div className="text-xs font-semibold text-text-secondary mb-1">
                                  Parsed Data
                                </div>
                                <div className="bg-background-subtle rounded-lg p-3 border border-border">
                                  <ReactJson
                                    src={Object.fromEntries(
                                      Object.entries(step.data).filter(([k]) => !['raw_request', 'raw_response'].includes(k))
                                    )}
                                    theme={jsonTheme}
                                    collapsed={3}
                                    displayDataTypes={false}
                                    displayObjectSize={true}
                                    enableClipboard={(copy) => {
                                      const value = copy.src
                                      const textToCopy = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
                                      navigator.clipboard.writeText(textToCopy)
                                    }}
                                    name="data"
                                    indentWidth={2}
                                    iconStyle="triangle"
                                    style={{
                                      backgroundColor: 'transparent',
                                      fontSize: '12px',
                                      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
                                    }}
                                  />
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              </>
            )}

            {!debugResult && !loading && (
              <div className="bg-surface-elevated rounded-xl border border-border p-12 text-center">
                <Shield className="text-text-disabled mx-auto mb-4" size={48} />
                <h3 className="text-lg font-medium text-text-primary mb-2">
                  No Debug Results Yet
                </h3>
                <p className="text-sm text-text-secondary">
                  Configure your authentication credentials and click "Debug Auth Flow" to see detailed step-by-step traces
                </p>
              </div>
            )}

            {/* Test Refresh Button - shown when OAuth with refresh fields */}
            {authType === 'oauth' && tokenUrl && (
              <TestRefreshButton
                tokenUrl={tokenUrl}
                refreshToken={bearerToken}
                clientId={clientId}
                clientSecret={clientSecret}
                onNewToken={(token) => setBearerToken(token)}
              />
            )}
          </div>
        </div>

        {/* JWT Token Decoder - full width below the two-column layout */}
        <JWTDecoder jsonTheme={jsonTheme} />

        {/* OAuth Flow Visualization Guide */}
        {authType === 'oauth' && !debugResult && !loading && (
          <div className="bg-surface-elevated rounded-xl border border-border p-6">
            <h3 className="text-lg font-semibold text-text-primary flex items-center gap-2 mb-4">
              <ArrowRight className="text-primary" size={20} />
              OAuth Flow Steps
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {[
                { step: '1. Authorize', desc: 'Client redirects user to authorization server', color: 'bg-green-500', icon: Lock },
                { step: '2. Callback', desc: 'Auth server redirects back with authorization code', color: 'bg-blue-500', icon: ArrowRight },
                { step: '3. Token', desc: 'Client exchanges code for access + refresh tokens', color: 'bg-orange-500', icon: Key },
                { step: '4. Refresh', desc: 'Use refresh token to get new access tokens', color: 'bg-purple-500', icon: RefreshCw },
              ].map(({ step, desc, color, icon: Icon }) => (
                <div key={step} className="p-4 bg-surface rounded-lg border border-border">
                  <div className="flex items-center gap-2 mb-2">
                    <div className={`p-1.5 ${color} rounded`}>
                      <Icon size={14} className="text-white" />
                    </div>
                    <span className="text-sm font-semibold text-text-primary">{step}</span>
                  </div>
                  <p className="text-xs text-text-secondary">{desc}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default AuthDebugger
