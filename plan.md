# FeatherJS WebSocket Integration Plan

**Status:** Planning Phase  
**Created:** 2025-10-31  
**Author:** Claude Code Assistant  

## Executive Summary

This document outlines the migration plan to integrate FeatherJS with Socket.io for real-time bidirectional communication in the testmcpy web application. The plan is based on comprehensive analysis of the Agor project's proven websocket architecture and the current testmcpy implementation.

---

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [FeatherJS Architecture Overview](#featherjs-architecture-overview)
3. [Target Architecture](#target-architecture)
4. [Migration Strategy](#migration-strategy)
5. [Implementation Plan](#implementation-plan)
6. [Security Considerations](#security-considerations)
7. [Testing Strategy](#testing-strategy)
8. [Rollout Plan](#rollout-plan)

---

## Current State Analysis

### testmcpy Current Implementation

#### Backend (FastAPI)
- **Framework:** FastAPI with Uvicorn
- **Current WebSocket:** Basic WebSocket support (`/ws` endpoint)
- **API Structure:** REST endpoints at `/api/*`
- **Chat System:** Simple request/response pattern with basic streaming
- **Test Runner:** Synchronous execution with manual polling

**File:** `testmcpy/server/api.py`
```python
- REST endpoints for chat, tests, MCP tools
- No real-time event broadcasting
- Manual state management
- Limited concurrency support
```

**File:** `testmcpy/server/websocket.py`
```python
- ConnectionManager for basic WebSocket handling
- Token-by-token streaming simulation
- Manual message broadcasting
- No event-driven architecture
```

#### Frontend (React + Vite)
- **Framework:** React 18 with Vite
- **State Management:** Local component state (useState)
- **API Communication:** Fetch API for REST calls
- **Real-time Updates:** Polling (no active WebSocket client)
- **UI Components:** Functional components with hooks

**Current Limitations:**
1. No real-time event broadcasting to multiple clients
2. Manual polling for test status updates
3. No multi-user collaboration support
4. Limited scalability for concurrent test runs
5. Basic chat streaming without proper event handling

### Agor Implementation (Reference Architecture)

#### Backend (FeathersJS + Express)
- **Framework:** FeathersJS 5.x with Express integration
- **WebSocket:** Socket.io 4.x with CORS configuration
- **Architecture:** Service-oriented with repository pattern
- **Event System:** Automatic CRUD event broadcasting
- **Real-time:** Channel-based publishing with WebSocket events

**Key Files:**
- `apps/agor-daemon/src/index.ts` - Main server setup
- `apps/agor-daemon/src/services/` - Service implementations
- `apps/agor-daemon/src/declarations.ts` - TypeScript types

**Proven Patterns:**
```typescript
// FeathersJS service with real-time events
app.configure(socketio({ cors: { origin: true } }));
app.on('connection', connection => {
  app.channel('everybody').join(connection);
});
app.publish(() => app.channel('everybody'));
```

#### Frontend (React + Vite + FeathersJS Client)
- **Client Library:** `@feathersjs/client` with Socket.io integration
- **Real-time Hooks:** Custom hooks for service subscriptions
- **Event Handling:** Service events (created, patched, updated, removed)
- **State Management:** React state with `flushSync()` for immediate updates

**Key Files:**
- `packages/core/src/api/index.ts` - Client creation
- `apps/agor-ui/src/hooks/useAgorClient.ts` - React integration
- `apps/agor-ui/src/hooks/useAgorData.ts` - Data subscriptions

**Proven Patterns:**
```typescript
// Real-time service subscription
messagesService.on('created', (message) => {
  flushSync(() => {
    setMessages(prev => [...prev, message].sort((a, b) => a.index - b.index));
  });
});
```

---

## FeatherJS Architecture Overview

### Core Concepts

#### 1. Service-Oriented Architecture
FeatherJS organizes functionality into **services** that provide CRUD operations:
- `find()` - Query/list resources
- `get(id)` - Retrieve single resource
- `create(data)` - Create new resource
- `update(id, data)` - Replace resource
- `patch(id, data)` - Partial update
- `remove(id)` - Delete resource

#### 2. Automatic Event Broadcasting
Every CRUD operation emits events:
- `created` - After create()
- `updated` - After update()
- `patched` - After patch()
- `removed` - After remove()

#### 3. Transport Agnostic
Same services work via:
- HTTP/REST
- WebSocket (Socket.io)
- Direct calls

#### 4. Hooks System
Middleware-like functions for:
- **Before hooks:** Validation, authentication
- **After hooks:** Transformation, side effects
- **Error hooks:** Error handling

### Technology Stack

```
┌─────────────────────────────────────────────┐
│           FeatherJS Application             │
├─────────────────────────────────────────────┤
│  Express (HTTP)    │   Socket.io (WS)       │
├─────────────────────────────────────────────┤
│            Service Layer                    │
│  - Messages    - Tests     - Chat           │
│  - Config      - Health    - Events         │
├─────────────────────────────────────────────┤
│         Repository/Data Layer               │
│  (Your existing business logic)             │
└─────────────────────────────────────────────┘
```

**Dependencies:**
```json
{
  "@feathersjs/feathers": "^5.0.0",
  "@feathersjs/express": "^5.0.0",
  "@feathersjs/socketio": "^5.0.0",
  "@feathersjs/authentication": "^5.0.0",
  "@feathersjs/authentication-local": "^5.0.0",
  "socket.io": "^4.7.0"
}
```

### Key Benefits for testmcpy

1. **Automatic Real-time Updates**
   - Test results broadcast to all connected clients
   - Chat messages appear instantly
   - Configuration changes propagate immediately

2. **Simplified Code**
   - No manual WebSocket management
   - No manual event emitters
   - Consistent API patterns

3. **Scalability**
   - Built-in channel system for targeting specific clients
   - Horizontal scaling support
   - Connection pooling

4. **Developer Experience**
   - Type-safe service definitions
   - Consistent client/server API
   - Rich ecosystem

---

## Target Architecture

### High-Level System Design

```
┌─────────────────────────────────────────────────────────┐
│                    React Frontend                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Chat View    │  │ Test Manager │  │ MCP Explorer │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                  │                  │           │
│         └──────────────────┼──────────────────┘           │
│                            │                              │
│                  ┌─────────▼────────┐                     │
│                  │ Feathers Client  │                     │
│                  │  (Socket.io)     │                     │
│                  └─────────┬────────┘                     │
└────────────────────────────┼──────────────────────────────┘
                             │
                    WebSocket Connection
                             │
┌────────────────────────────▼──────────────────────────────┐
│              FeatherJS Backend (Python)                    │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              Express + Socket.io                     │  │
│  └───────────────────────┬─────────────────────────────┘  │
│                          │                                 │
│  ┌───────────────────────▼─────────────────────────────┐  │
│  │                 Service Layer                        │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐            │  │
│  │  │ Messages │ │  Tests   │ │   Chat   │            │  │
│  │  └──────────┘ └──────────┘ └──────────┘            │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐            │  │
│  │  │   MCP    │ │  Config  │ │  Health  │            │  │
│  │  └──────────┘ └──────────┘ └──────────┘            │  │
│  └───────────────────────┬─────────────────────────────┘  │
│                          │                                 │
│  ┌───────────────────────▼─────────────────────────────┐  │
│  │         Existing Business Logic                      │  │
│  │  TestRunner │ MCPClient │ LLMIntegration            │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### Service Definitions

#### 1. Messages Service
**Purpose:** Chat message management with streaming

**Methods:**
- `find({ query })` - Get message history
- `create(data)` - Send new message
- `patch(id, data)` - Update message (e.g., add tool results)
- `remove(id)` - Delete message

**Events:**
- `messages created` - New message sent
- `messages patched` - Message updated (tool results)
- `messages streaming:chunk` - Real-time token streaming

**Implementation:**
```python
class MessagesService:
    async def create(self, data, params):
        # Create message
        message = await self.repository.create(data)
        
        # Emit created event (automatic)
        # All clients receive via 'messages created' event
        
        return message
    
    async def stream_response(self, message_id, llm_stream):
        # Custom streaming method
        async for chunk in llm_stream:
            self.emit('streaming:chunk', {
                'message_id': message_id,
                'chunk': chunk
            })
```

#### 2. Tests Service
**Purpose:** Test execution and result management

**Methods:**
- `find({ query })` - List tests
- `get(id)` - Get test details
- `create(data)` - Create test
- `patch(id, data)` - Update test (e.g., results)
- `remove(id)` - Delete test

**Events:**
- `tests created` - New test created
- `tests patched` - Test updated (progress, results)
- `tests status:update` - Real-time status updates

**Implementation:**
```python
class TestsService:
    async def run_test(self, test_id):
        # Start test execution
        test = await self.get(test_id)
        
        # Update status to running
        await self.patch(test_id, {'status': 'running'})
        # Emits 'tests patched' automatically
        
        # Run test in background
        asyncio.create_task(self._execute_test(test_id))
        
        return test
    
    async def _execute_test(self, test_id):
        # Execute test
        result = await self.test_runner.run(test_id)
        
        # Update with results
        await self.patch(test_id, {
            'status': 'completed',
            'result': result
        })
        # Emits 'tests patched' automatically
```

#### 3. Chat Service
**Purpose:** High-level chat session management

**Methods:**
- `create(data)` - Start chat session
- `patch(id, data)` - Update session state

**Events:**
- `chat created` - New session
- `chat patched` - Session updated

### Event Flow Examples

#### Example 1: Chat Message with Tool Execution

```
┌────────┐         ┌────────┐         ┌────────┐
│ Client │         │ Server │         │  LLM   │
└───┬────┘         └───┬────┘         └───┬────┘
    │                  │                  │
    │ POST /messages   │                  │
    ├─────────────────>│                  │
    │                  │                  │
    │                  │ Start streaming  │
    │                  ├─────────────────>│
    │                  │                  │
    │ Event: created   │                  │
    │<─────────────────┤                  │
    │                  │                  │
    │                  │ Stream chunk     │
    │                  │<─────────────────┤
    │ Event: chunk     │                  │
    │<─────────────────┤                  │
    │                  │                  │
    │ Event: chunk     │                  │
    │<─────────────────┤                  │
    │                  │                  │
    │                  │ Tool call needed │
    │                  │<─────────────────┤
    │ Event: tool_call │                  │
    │<─────────────────┤                  │
    │                  │                  │
    │                  │ Execute tool     │
    │                  │ (MCP Client)     │
    │                  │                  │
    │ Event: patched   │                  │
    │ (tool_result)    │                  │
    │<─────────────────┤                  │
    │                  │                  │
    │ Event: complete  │                  │
    │<─────────────────┤                  │
```

#### Example 2: Test Execution with Real-time Updates

```
┌────────┐         ┌────────┐         ┌────────┐
│ Client │         │ Server │         │ Runner │
└───┬────┘         └───┬────┘         └───┬────┘
    │                  │                  │
    │ POST /tests/run  │                  │
    ├─────────────────>│                  │
    │                  │                  │
    │ Event: patched   │                  │
    │ (status:running) │                  │
    │<─────────────────┤                  │
    │                  │                  │
    │                  │ Start test       │
    │                  ├─────────────────>│
    │                  │                  │
    │                  │ Progress update  │
    │                  │<─────────────────┤
    │ Event: patched   │                  │
    │ (progress: 25%)  │                  │
    │<─────────────────┤                  │
    │                  │                  │
    │                  │ Progress update  │
    │                  │<─────────────────┤
    │ Event: patched   │                  │
    │ (progress: 50%)  │                  │
    │<─────────────────┤                  │
    │                  │                  │
    │                  │ Test complete    │
    │                  │<─────────────────┤
    │ Event: patched   │                  │
    │ (status:complete)│                  │
    │<─────────────────┤                  │
```

---

## Migration Strategy

### Phase 1: Foundation (Week 1)

**Goal:** Set up FeatherJS infrastructure alongside existing FastAPI

**Tasks:**
1. Install FeatherJS dependencies (Python port or Node.js microservice)
2. Create service base classes
3. Set up Socket.io server
4. Configure CORS and authentication
5. Create health check service

**Deliverables:**
- FeatherJS server running on separate port (e.g., 8001)
- Basic service infrastructure
- Socket.io WebSocket endpoint
- Health check endpoint

**Risk Mitigation:**
- Keep FastAPI running in parallel
- No changes to existing endpoints
- Feature flag for switching between APIs

### Phase 2: Core Services (Week 2)

**Goal:** Implement core services with real-time events

**Tasks:**
1. Messages service implementation
2. Tests service implementation
3. Chat service implementation
4. MCP tools service (read-only)
5. Configuration service

**Deliverables:**
- CRUD operations for all services
- Automatic event broadcasting
- Service hooks for validation
- Integration with existing business logic

**Risk Mitigation:**
- Write integration tests for each service
- Test event broadcasting
- Validate backward compatibility

### Phase 3: Frontend Integration (Week 3)

**Goal:** Connect React frontend to FeatherJS backend

**Tasks:**
1. Install `@feathersjs/client` and `socket.io-client`
2. Create Feathers client configuration
3. Implement useFeathersClient hook
4. Implement useFeathersService hook
5. Migrate Chat component to use real-time events
6. Migrate Test Manager to use real-time events

**Deliverables:**
- React hooks for Feathers integration
- Real-time chat updates
- Real-time test progress updates
- Backward compatible with REST API

**Risk Mitigation:**
- Progressive rollout per component
- Feature flags for old/new implementations
- Comprehensive component testing

### Phase 4: Advanced Features (Week 4)

**Goal:** Leverage FeatherJS for advanced real-time features

**Tasks:**
1. Implement streaming responses for chat
2. Add real-time test progress indicators
3. Multi-client synchronization
4. Optimistic UI updates
5. Connection resilience

**Deliverables:**
- Smooth streaming experience
- Real-time progress bars
- Multi-tab synchronization
- Auto-reconnection logic

**Risk Mitigation:**
- Performance testing with multiple clients
- Network resilience testing
- Load testing

### Phase 5: Migration Completion (Week 5)

**Goal:** Deprecate FastAPI WebSocket, switch to FeatherJS

**Tasks:**
1. Remove old WebSocket implementation
2. Remove polling code
3. Update documentation
4. Performance optimization
5. Production deployment

**Deliverables:**
- Clean codebase
- Updated documentation
- Production-ready deployment
- Migration guide

---

## Implementation Plan

### Backend Implementation

#### Directory Structure
```
testmcpy/
├── server/
│   ├── feathers/
│   │   ├── __init__.py
│   │   ├── app.py              # FeatherJS application setup
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── messages.py     # Messages service
│   │   │   ├── tests.py        # Tests service
│   │   │   ├── chat.py         # Chat service
│   │   │   ├── mcp_tools.py    # MCP tools service
│   │   │   └── config.py       # Configuration service
│   │   ├── hooks/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py         # Authentication hooks
│   │   │   └── validation.py   # Validation hooks
│   │   └── channels.py         # Channel configuration
│   ├── api.py                  # Existing FastAPI (deprecated)
│   └── websocket.py            # Existing WebSocket (deprecated)
```

#### Key Implementation Files

**File: `testmcpy/server/feathers/app.py`**
```python
"""
FeatherJS application setup for testmcpy.
"""
from feathers import Feathers
from feathers_express import express
from feathers_socketio import socketio
import socketio as sio

def create_app():
    # Create Feathers app
    app = Feathers()
    
    # Configure Express
    app = express(app)
    
    # Configure CORS
    app.use(cors({
        'origin': ['http://localhost:5173', 'http://localhost:8000'],
        'credentials': True
    }))
    
    # Configure Socket.io
    app.configure(socketio({
        'cors': {
            'origin': '*',
            'credentials': True
        },
        'pingTimeout': 60000,
        'pingInterval': 25000,
        'transports': ['websocket', 'polling']
    }))
    
    # Configure channels
    @app.on('connection')
    def on_connection(connection):
        app.channel('everybody').join(connection)
    
    @app.publish()
    def publish_all(data, context):
        return app.channel('everybody')
    
    # Register services
    from .services.messages import MessagesService
    from .services.tests import TestsService
    from .services.chat import ChatService
    from .services.mcp_tools import MCPToolsService
    from .services.config import ConfigService
    
    app.use('/messages', MessagesService())
    app.use('/tests', TestsService())
    app.use('/chat', ChatService())
    app.use('/mcp-tools', MCPToolsService())
    app.use('/config', ConfigService())
    
    # Error handling
    @app.error_handler
    def handle_error(error):
        return {
            'error': str(error),
            'name': error.__class__.__name__
        }
    
    return app
```

**File: `testmcpy/server/feathers/services/messages.py`**
```python
"""
Messages service for chat functionality.
"""
from feathers import Service
import asyncio

class MessagesService(Service):
    """Handle chat messages with streaming support."""
    
    def __init__(self):
        super().__init__()
        self.messages = []  # In-memory store (replace with DB)
    
    async def find(self, params=None):
        """Get message history."""
        query = params.get('query', {}) if params else {}
        
        # Filter by session_id if provided
        session_id = query.get('session_id')
        if session_id:
            return [m for m in self.messages if m.get('session_id') == session_id]
        
        return self.messages
    
    async def create(self, data, params=None):
        """Create new message."""
        message = {
            'id': len(self.messages) + 1,
            'content': data.get('content'),
            'role': data.get('role', 'user'),
            'session_id': data.get('session_id'),
            'created_at': datetime.now().isoformat()
        }
        
        self.messages.append(message)
        
        # If this is a user message, start LLM processing
        if message['role'] == 'user':
            asyncio.create_task(self._process_llm_response(message))
        
        return message
    
    async def _process_llm_response(self, user_message):
        """Process LLM response with streaming."""
        from testmcpy.src.llm_integration import create_llm_provider
        from testmcpy.src.mcp_client import MCPClient
        
        # Get MCP tools
        mcp_client = MCPClient()
        await mcp_client.initialize()
        tools = await mcp_client.list_tools()
        
        # Format tools for LLM
        formatted_tools = [
            {
                'type': 'function',
                'function': {
                    'name': tool.name,
                    'description': tool.description,
                    'parameters': tool.input_schema
                }
            }
            for tool in tools
        ]
        
        # Create assistant message
        assistant_message = {
            'id': len(self.messages) + 1,
            'content': '',
            'role': 'assistant',
            'session_id': user_message['session_id'],
            'created_at': datetime.now().isoformat()
        }
        self.messages.append(assistant_message)
        
        # Emit created event
        self.emit('created', assistant_message)
        
        # Get LLM provider
        llm_provider = create_llm_provider('anthropic', 'claude-haiku-4-5')
        await llm_provider.initialize()
        
        try:
            # Stream response
            async for chunk in llm_provider.stream_with_tools(
                prompt=user_message['content'],
                tools=formatted_tools
            ):
                # Emit streaming chunk
                self.emit('streaming:chunk', {
                    'message_id': assistant_message['id'],
                    'chunk': chunk.get('content', ''),
                    'tool_calls': chunk.get('tool_calls', [])
                })
                
                # Update message content
                assistant_message['content'] += chunk.get('content', '')
            
            # Execute tool calls if any
            tool_calls = chunk.get('tool_calls', [])
            if tool_calls:
                for tool_call in tool_calls:
                    # Emit tool call event
                    self.emit('tool:call', {
                        'message_id': assistant_message['id'],
                        'tool_name': tool_call['name'],
                        'arguments': tool_call['arguments']
                    })
                    
                    # Execute tool
                    result = await mcp_client.call_tool(tool_call)
                    
                    # Emit tool result event
                    self.emit('tool:result', {
                        'message_id': assistant_message['id'],
                        'tool_name': tool_call['name'],
                        'result': result.content
                    })
            
            # Emit completion
            self.emit('streaming:complete', {
                'message_id': assistant_message['id']
            })
            
            # Update message with final state
            await self.patch(assistant_message['id'], {
                'status': 'complete',
                'tool_calls': tool_calls
            })
            
        except Exception as e:
            # Emit error
            self.emit('streaming:error', {
                'message_id': assistant_message['id'],
                'error': str(e)
            })
            
            await self.patch(assistant_message['id'], {
                'status': 'error',
                'error': str(e)
            })
        
        finally:
            await llm_provider.close()
            await mcp_client.close()
```

**File: `testmcpy/server/feathers/services/tests.py`**
```python
"""
Tests service for test execution and management.
"""
from feathers import Service
import asyncio

class TestsService(Service):
    """Handle test execution with real-time progress."""
    
    def __init__(self):
        super().__init__()
        self.tests = []
    
    async def find(self, params=None):
        """List tests."""
        return self.tests
    
    async def get(self, id, params=None):
        """Get test by ID."""
        test = next((t for t in self.tests if t['id'] == id), None)
        if not test:
            raise Exception(f'Test {id} not found')
        return test
    
    async def create(self, data, params=None):
        """Create new test."""
        test = {
            'id': len(self.tests) + 1,
            'name': data.get('name'),
            'prompt': data.get('prompt'),
            'evaluators': data.get('evaluators', []),
            'status': 'created',
            'created_at': datetime.now().isoformat()
        }
        
        self.tests.append(test)
        return test
    
    async def patch(self, id, data, params=None):
        """Update test (used for status updates)."""
        test = await self.get(id)
        test.update(data)
        return test
    
    async def run_test(self, id):
        """Execute test with real-time updates."""
        test = await self.get(id)
        
        # Update status to running
        await self.patch(id, {'status': 'running', 'progress': 0})
        
        # Run test in background
        asyncio.create_task(self._execute_test(id))
        
        return test
    
    async def _execute_test(self, test_id):
        """Execute test and emit progress updates."""
        from testmcpy.src.test_runner import TestRunner, TestCase
        
        test = await self.get(test_id)
        
        try:
            # Create test case
            test_case = TestCase(
                name=test['name'],
                prompt=test['prompt'],
                evaluators=test['evaluators']
            )
            
            # Create runner
            runner = TestRunner(
                model='claude-haiku-4-5',
                provider='anthropic'
            )
            
            # Initialize
            await runner.initialize()
            
            # Update progress: Initialized
            await self.patch(test_id, {'progress': 10})
            
            # Run test
            result = await runner.run_test(test_case)
            
            # Update progress: Test execution complete
            await self.patch(test_id, {'progress': 90})
            
            # Update with results
            await self.patch(test_id, {
                'status': 'complete',
                'progress': 100,
                'result': result.to_dict()
            })
            
        except Exception as e:
            # Update with error
            await self.patch(test_id, {
                'status': 'failed',
                'error': str(e)
            })
        
        finally:
            await runner.cleanup()
```

### Frontend Implementation

#### Directory Structure
```
testmcpy/ui/src/
├── lib/
│   ├── feathers.ts           # Feathers client setup
│   └── types.ts              # TypeScript types
├── hooks/
│   ├── useFeathersClient.ts  # Client lifecycle hook
│   ├── useFeathersService.ts # Service subscription hook
│   ├── useMessages.ts        # Messages service hook
│   ├── useTests.ts           # Tests service hook
│   └── useRealtime.ts        # Real-time event hook
├── pages/
│   ├── ChatInterface.tsx     # Updated chat component
│   └── TestManager.tsx       # Updated test manager
```

#### Key Implementation Files

**File: `testmcpy/ui/src/lib/feathers.ts`**
```typescript
/**
 * Feathers client configuration
 */
import feathers from '@feathersjs/client';
import socketio from '@feathersjs/socketio-client';
import io from 'socket.io-client';

// Service types
export interface Message {
  id: number;
  content: string;
  role: 'user' | 'assistant' | 'system';
  session_id?: string;
  created_at: string;
  status?: string;
  tool_calls?: any[];
  error?: string;
}

export interface Test {
  id: number;
  name: string;
  prompt: string;
  evaluators: any[];
  status: string;
  progress?: number;
  result?: any;
  error?: string;
  created_at: string;
}

export interface ServiceTypes {
  messages: Message;
  tests: Test;
  chat: any;
  'mcp-tools': any;
  config: any;
}

export function createFeathersClient(url: string = 'http://localhost:8001') {
  // Create Socket.io socket
  const socket = io(url, {
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionAttempts: 5
  });
  
  // Create Feathers app
  const client = feathers<ServiceTypes>();
  
  // Configure Socket.io transport
  client.configure(socketio(socket));
  
  // Expose socket for connection management
  (client as any).io = socket;
  
  return client;
}
```

**File: `testmcpy/ui/src/hooks/useFeathersClient.ts`**
```typescript
/**
 * React hook for Feathers client lifecycle
 */
import { useState, useEffect, useRef } from 'react';
import { createFeathersClient } from '../lib/feathers';

export function useFeathersClient(url?: string) {
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const clientRef = useRef<any>(null);
  
  useEffect(() => {
    // Create client
    const client = createFeathersClient(url);
    clientRef.current = client;
    
    // Setup socket events
    client.io.on('connect', () => {
      console.log('Connected to Feathers server');
      setConnected(true);
      setError(null);
    });
    
    client.io.on('disconnect', () => {
      console.log('Disconnected from Feathers server');
      setConnected(false);
    });
    
    client.io.on('connect_error', (err: Error) => {
      console.error('Connection error:', err);
      setError('Failed to connect to server');
      setConnected(false);
    });
    
    // Connect
    client.io.connect();
    
    // Cleanup
    return () => {
      client.io.removeAllListeners();
      client.io.close();
    };
  }, [url]);
  
  return {
    client: clientRef.current,
    connected,
    error
  };
}
```

**File: `testmcpy/ui/src/hooks/useMessages.ts`**
```typescript
/**
 * React hook for real-time messages
 */
import { useState, useEffect } from 'react';
import { flushSync } from 'react-dom';
import type { Message } from '../lib/feathers';

export function useMessages(client: any, sessionId?: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState<number | null>(null);
  
  useEffect(() => {
    if (!client) return;
    
    const messagesService = client.service('messages');
    
    // Load initial messages
    const loadMessages = async () => {
      setLoading(true);
      try {
        const result = await messagesService.find({
          query: sessionId ? { session_id: sessionId } : {}
        });
        setMessages(result);
      } catch (err) {
        console.error('Failed to load messages:', err);
      } finally {
        setLoading(false);
      }
    };
    
    loadMessages();
    
    // Subscribe to real-time events
    const handleCreated = (message: Message) => {
      if (!sessionId || message.session_id === sessionId) {
        flushSync(() => {
          setMessages(prev => [...prev, message]);
        });
      }
    };
    
    const handlePatched = (message: Message) => {
      if (!sessionId || message.session_id === sessionId) {
        flushSync(() => {
          setMessages(prev =>
            prev.map(m => m.id === message.id ? message : m)
          );
        });
      }
    };
    
    const handleStreamingChunk = (data: any) => {
      flushSync(() => {
        setStreamingMessageId(data.message_id);
        setMessages(prev =>
          prev.map(m =>
            m.id === data.message_id
              ? { ...m, content: m.content + data.chunk }
              : m
          )
        );
      });
    };
    
    const handleStreamingComplete = (data: any) => {
      setStreamingMessageId(null);
    };
    
    const handleToolCall = (data: any) => {
      console.log('Tool call:', data);
      // Update UI to show tool is being executed
    };
    
    const handleToolResult = (data: any) => {
      console.log('Tool result:', data);
      // Update UI to show tool result
    };
    
    // Register event listeners
    messagesService.on('created', handleCreated);
    messagesService.on('patched', handlePatched);
    messagesService.on('streaming:chunk', handleStreamingChunk);
    messagesService.on('streaming:complete', handleStreamingComplete);
    messagesService.on('tool:call', handleToolCall);
    messagesService.on('tool:result', handleToolResult);
    
    // Cleanup
    return () => {
      messagesService.removeListener('created', handleCreated);
      messagesService.removeListener('patched', handlePatched);
      messagesService.removeListener('streaming:chunk', handleStreamingChunk);
      messagesService.removeListener('streaming:complete', handleStreamingComplete);
      messagesService.removeListener('tool:call', handleToolCall);
      messagesService.removeListener('tool:result', handleToolResult);
    };
  }, [client, sessionId]);
  
  const sendMessage = async (content: string) => {
    if (!client) return;
    
    const messagesService = client.service('messages');
    await messagesService.create({
      content,
      role: 'user',
      session_id: sessionId
    });
  };
  
  return {
    messages,
    loading,
    streamingMessageId,
    sendMessage
  };
}
```

**File: `testmcpy/ui/src/hooks/useTests.ts`**
```typescript
/**
 * React hook for real-time tests
 */
import { useState, useEffect } from 'react';
import { flushSync } from 'react-dom';
import type { Test } from '../lib/feathers';

export function useTests(client: any) {
  const [tests, setTests] = useState<Test[]>([]);
  const [loading, setLoading] = useState(false);
  
  useEffect(() => {
    if (!client) return;
    
    const testsService = client.service('tests');
    
    // Load initial tests
    const loadTests = async () => {
      setLoading(true);
      try {
        const result = await testsService.find();
        setTests(result);
      } catch (err) {
        console.error('Failed to load tests:', err);
      } finally {
        setLoading(false);
      }
    };
    
    loadTests();
    
    // Subscribe to real-time events
    const handleCreated = (test: Test) => {
      flushSync(() => {
        setTests(prev => [...prev, test]);
      });
    };
    
    const handlePatched = (test: Test) => {
      flushSync(() => {
        setTests(prev =>
          prev.map(t => t.id === test.id ? test : t)
        );
      });
    };
    
    const handleRemoved = (test: Test) => {
      flushSync(() => {
        setTests(prev => prev.filter(t => t.id !== test.id));
      });
    };
    
    // Register event listeners
    testsService.on('created', handleCreated);
    testsService.on('patched', handlePatched);
    testsService.on('removed', handleRemoved);
    
    // Cleanup
    return () => {
      testsService.removeListener('created', handleCreated);
      testsService.removeListener('patched', handlePatched);
      testsService.removeListener('removed', handleRemoved);
    };
  }, [client]);
  
  const runTest = async (testId: number) => {
    if (!client) return;
    
    const testsService = client.service('tests');
    // Call custom method to run test
    await testsService.patch(testId, { action: 'run' });
  };
  
  const createTest = async (data: Partial<Test>) => {
    if (!client) return;
    
    const testsService = client.service('tests');
    await testsService.create(data);
  };
  
  return {
    tests,
    loading,
    runTest,
    createTest
  };
}
```

**File: `testmcpy/ui/src/pages/ChatInterface.tsx` (Updated)**
```typescript
/**
 * Updated Chat Interface using FeatherJS
 */
import React, { useState } from 'react';
import { useFeathersClient } from '../hooks/useFeathersClient';
import { useMessages } from '../hooks/useMessages';

export default function ChatInterface() {
  const { client, connected, error } = useFeathersClient();
  const { messages, loading, streamingMessageId, sendMessage } = useMessages(client);
  const [input, setInput] = useState('');
  
  const handleSend = async () => {
    if (!input.trim()) return;
    
    await sendMessage(input);
    setInput('');
  };
  
  return (
    <div className="flex flex-col h-full">
      {/* Connection Status */}
      {!connected && (
        <div className="bg-yellow-500 text-white p-2 text-center">
          {error || 'Connecting to server...'}
        </div>
      )}
      
      {/* Messages */}
      <div className="flex-1 overflow-auto p-4">
        {messages.map(message => (
          <div
            key={message.id}
            className={`mb-4 ${message.role === 'user' ? 'text-right' : 'text-left'}`}
          >
            <div
              className={`inline-block p-3 rounded-lg ${
                message.role === 'user'
                  ? 'bg-blue-500 text-white'
                  : 'bg-gray-200'
              }`}
            >
              {message.content}
              
              {/* Streaming indicator */}
              {streamingMessageId === message.id && (
                <span className="ml-2 animate-pulse">▋</span>
              )}
              
              {/* Tool calls */}
              {message.tool_calls && message.tool_calls.length > 0 && (
                <div className="mt-2 text-xs opacity-75">
                  🔧 Used {message.tool_calls.length} tool(s)
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
      
      {/* Input */}
      <div className="p-4 border-t">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyPress={e => e.key === 'Enter' && handleSend()}
            placeholder="Type a message..."
            className="flex-1 p-2 border rounded"
            disabled={!connected}
          />
          <button
            onClick={handleSend}
            disabled={!connected || !input.trim()}
            className="px-4 py-2 bg-blue-500 text-white rounded disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
```

---

## Security Considerations

### 1. Authentication & Authorization

**Current State:**
- No authentication in testmcpy
- Open access to all endpoints

**FeatherJS Solution:**
```python
from feathers_authentication import AuthenticationService
from feathers_authentication_local import LocalStrategy

# Configure authentication
app.configure(authentication({
    'secret': 'your-secret-key',
    'entity': 'user',
    'service': 'users',
    'authStrategies': ['jwt', 'local']
}))

# Protect services with hooks
@app.service('messages').before('create')
def require_auth(context):
    if not context.params.get('user'):
        raise Unauthorized('Authentication required')
    return context
```

**Recommendations:**
1. Implement JWT-based authentication
2. Add user management service
3. Protect sensitive endpoints
4. Rate limiting per user

### 2. CORS Configuration

**Current State:**
- Allow all origins (`*`)

**Production Configuration:**
```python
app.configure(socketio({
    'cors': {
        'origin': [
            'https://yourdomain.com',
            'http://localhost:5173'  # Development only
        ],
        'credentials': True,
        'methods': ['GET', 'POST', 'PATCH', 'DELETE']
    }
}))
```

### 3. Input Validation

**Service-level validation:**
```python
class MessagesService(Service):
    async def create(self, data, params=None):
        # Validate input
        if not data.get('content'):
            raise ValidationError('Message content required')
        
        if len(data['content']) > 10000:
            raise ValidationError('Message too long (max 10000 chars)')
        
        # Sanitize HTML
        data['content'] = sanitize_html(data['content'])
        
        return await super().create(data, params)
```

### 4. Rate Limiting

**WebSocket connection limits:**
```python
from feathers_rate_limit import RateLimitHook

# Apply rate limiting
app.service('messages').before('create', RateLimitHook({
    'max_requests': 10,
    'window_ms': 60000  # 10 requests per minute
}))
```

### 5. Error Handling

**Avoid leaking sensitive info:**
```python
@app.error_handler
def handle_error(error):
    # Log full error server-side
    logger.error(f'Service error: {error}', exc_info=True)
    
    # Return sanitized error to client
    return {
        'error': 'An error occurred',
        'code': error.code if hasattr(error, 'code') else 500
    }
```

---

## Testing Strategy

### Unit Tests

**Backend Service Tests:**
```python
# tests/services/test_messages.py
import pytest
from testmcpy.server.feathers.services.messages import MessagesService

@pytest.fixture
async def messages_service():
    service = MessagesService()
    await service.setup()
    return service

@pytest.mark.asyncio
async def test_create_message(messages_service):
    message = await messages_service.create({
        'content': 'Hello',
        'role': 'user',
        'session_id': 'test-session'
    })
    
    assert message['content'] == 'Hello'
    assert message['role'] == 'user'
    assert message['id'] is not None

@pytest.mark.asyncio
async def test_find_messages_by_session(messages_service):
    # Create messages
    await messages_service.create({
        'content': 'Message 1',
        'session_id': 'session-1'
    })
    await messages_service.create({
        'content': 'Message 2',
        'session_id': 'session-2'
    })
    
    # Find by session
    messages = await messages_service.find({
        'query': {'session_id': 'session-1'}
    })
    
    assert len(messages) == 1
    assert messages[0]['content'] == 'Message 1'
```

**Frontend Hook Tests:**
```typescript
// tests/hooks/useMessages.test.ts
import { renderHook, waitFor } from '@testing-library/react';
import { useMessages } from '../src/hooks/useMessages';

describe('useMessages', () => {
  it('loads initial messages', async () => {
    const mockClient = createMockClient();
    
    const { result } = renderHook(() => useMessages(mockClient));
    
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
    
    expect(result.current.messages).toHaveLength(2);
  });
  
  it('receives real-time message', async () => {
    const mockClient = createMockClient();
    
    const { result } = renderHook(() => useMessages(mockClient));
    
    // Simulate service event
    mockClient.service('messages').emit('created', {
      id: 3,
      content: 'New message',
      role: 'user'
    });
    
    await waitFor(() => {
      expect(result.current.messages).toHaveLength(3);
    });
  });
});
```

### Integration Tests

**End-to-End Test:**
```python
# tests/integration/test_chat_flow.py
import pytest
from playwright.async_api import async_playwright

@pytest.mark.asyncio
async def test_full_chat_flow():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        # Navigate to chat
        await page.goto('http://localhost:8000/chat')
        
        # Wait for connection
        await page.wait_for_selector('.connection-status.connected')
        
        # Type message
        await page.fill('input[type="text"]', 'Create a bar chart')
        await page.click('button:has-text("Send")')
        
        # Wait for response
        await page.wait_for_selector('.message.assistant')
        
        # Verify tool call
        tool_call = await page.text_content('.tool-call')
        assert 'create_chart' in tool_call
        
        await browser.close()
```

### Performance Tests

**Load Testing:**
```python
# tests/performance/test_websocket_load.py
import asyncio
from locust import User, task, between
from socketio import AsyncClient

class WebSocketUser(User):
    wait_time = between(1, 5)
    
    async def on_start(self):
        self.sio = AsyncClient()
        await self.sio.connect('http://localhost:8001')
    
    @task
    async def send_message(self):
        await self.sio.emit('create', {
            'service': 'messages',
            'data': {
                'content': 'Test message',
                'role': 'user'
            }
        })
    
    async def on_stop(self):
        await self.sio.disconnect()
```

---

## Rollout Plan

### Phase 1: Canary Deployment (10% of users)

**Week 1:**
1. Deploy FeatherJS backend alongside FastAPI
2. Enable feature flag for 10% of users
3. Monitor metrics:
   - WebSocket connection success rate
   - Event delivery latency
   - Error rates
   - CPU/memory usage

**Rollback Criteria:**
- WebSocket connection success < 95%
- Event delivery latency > 500ms
- Error rate > 1%
- Memory leaks detected

### Phase 2: Gradual Rollout (50% of users)

**Week 2:**
1. Increase feature flag to 50%
2. Continue monitoring
3. Gather user feedback
4. Fix any issues

**Success Criteria:**
- Connection success > 98%
- Latency < 200ms
- Error rate < 0.5%
- Positive user feedback

### Phase 3: Full Rollout (100% of users)

**Week 3:**
1. Enable for all users
2. Monitor for 48 hours
3. Deprecation notice for old API

### Phase 4: Cleanup

**Week 4:**
1. Remove FastAPI WebSocket code
2. Remove feature flags
3. Update documentation
4. Celebrate! 🎉

---

## Appendix

### A. Dependencies

**Python (Backend):**
```txt
# FeatherJS (Python port - hypothetical, may need Node.js bridge)
feathers>=5.0.0
feathers-express>=5.0.0
feathers-socketio>=5.0.0
feathers-authentication>=5.0.0
python-socketio>=5.10.0

# Existing dependencies
fastapi>=0.104.0
uvicorn>=0.24.0
websockets>=12.0
```

**JavaScript/TypeScript (Frontend):**
```json
{
  "dependencies": {
    "@feathersjs/feathers": "^5.0.0",
    "@feathersjs/client": "^5.0.0",
    "@feathersjs/socketio-client": "^5.0.0",
    "socket.io-client": "^4.7.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  }
}
```

**Note:** FeatherJS is primarily a Node.js framework. For Python integration, consider:
1. **Option A:** Use Node.js microservice for FeatherJS layer
2. **Option B:** Use Python Socket.io with FeatherJS-inspired patterns
3. **Option C:** Hybrid approach with FastAPI + python-socketio

### B. Alternative: Python-Native Approach

If FeatherJS Python port is not available, use python-socketio with FeatherJS patterns:

**Backend:**
```python
import socketio
from fastapi import FastAPI

# Create Socket.io server
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*'
)

app = FastAPI()
socket_app = socketio.ASGIApp(sio, app)

# Service pattern
class MessagesService:
    async def create(self, data):
        message = {...}
        # Emit event
        await sio.emit('messages created', message)
        return message

@sio.event
async def create_message(sid, data):
    service = MessagesService()
    return await service.create(data)
```

**Frontend:** (Same FeatherJS client with custom adapter)

### C. Monitoring & Observability

**Metrics to Track:**
1. **Connection Metrics:**
   - Active WebSocket connections
   - Connection success rate
   - Reconnection attempts
   - Average connection duration

2. **Performance Metrics:**
   - Event delivery latency (p50, p95, p99)
   - Message throughput (msg/sec)
   - Service response time
   - CPU/memory usage

3. **Business Metrics:**
   - Messages sent per user
   - Test execution rate
   - Tool call frequency
   - User engagement

**Tools:**
- Prometheus for metrics collection
- Grafana for visualization
- Sentry for error tracking
- LogRocket for session replay

### D. Migration Checklist

- [ ] Phase 1: Foundation
  - [ ] Install dependencies
  - [ ] Create service base classes
  - [ ] Set up Socket.io server
  - [ ] Configure CORS
  - [ ] Health check endpoint

- [ ] Phase 2: Core Services
  - [ ] Messages service
  - [ ] Tests service
  - [ ] Chat service
  - [ ] MCP tools service
  - [ ] Configuration service

- [ ] Phase 3: Frontend Integration
  - [ ] Install client libraries
  - [ ] Create Feathers client
  - [ ] Implement hooks
  - [ ] Update Chat component
  - [ ] Update Test Manager component

- [ ] Phase 4: Advanced Features
  - [ ] Streaming responses
  - [ ] Progress indicators
  - [ ] Multi-client sync
  - [ ] Optimistic updates

- [ ] Phase 5: Completion
  - [ ] Remove old code
  - [ ] Update docs
  - [ ] Performance optimization
  - [ ] Production deployment

---

## Conclusion

This plan provides a comprehensive roadmap for integrating FeatherJS and Socket.io into the testmcpy web application. The architecture is proven by the Agor project and offers significant benefits:

- **Real-time Communication:** Instant updates for chat and test execution
- **Simplified Codebase:** Service-oriented architecture with automatic events
- **Scalability:** Built-in support for multiple clients and channels
- **Developer Experience:** Type-safe APIs and consistent patterns

**Next Steps:**
1. Review and approve this plan
2. Set up development environment
3. Start Phase 1 implementation
4. Iterate based on feedback

**Questions?** Contact the development team or create an issue in the repository.
