# testmcpy Web Server Guide

This guide covers the new web server feature for testmcpy, which provides a beautiful React-based UI for inspecting and testing MCP servers.

## Overview

The web server feature adds a modern, interactive web interface to testmcpy, making it easier to:

- Browse MCP tools, resources, and prompts
- Chat interactively with LLMs that use MCP tools
- Create, edit, and run test files visually
- View configuration settings

## Installation

Install testmcpy with server support:

```bash
pip install 'testmcpy[server]'
```

This installs the additional dependencies needed for the web server:
- FastAPI
- Uvicorn
- WebSockets

## Quick Start

Start the web server:

```bash
testmcpy serve
```

This will:
1. Build the React frontend (if not already built)
2. Start the FastAPI server on http://localhost:8000
3. Automatically open your browser

## Command Options

```bash
testmcpy serve [OPTIONS]
```

Options:
- `--port, -p INTEGER`: Port to run server on (default: 8000)
- `--host TEXT`: Host to bind to (default: 127.0.0.1)
- `--dev`: Run in development mode (frontend must be started separately)
- `--no-browser`: Don't open browser automatically

### Examples

Run on a different port:
```bash
testmcpy serve --port 3000
```

Run on all interfaces:
```bash
testmcpy serve --host 0.0.0.0
```

Development mode (for UI development):
```bash
# Terminal 1: Start backend
testmcpy serve --dev --no-browser

# Terminal 2: Start frontend
cd testmcpy/ui
npm run dev
```

## Architecture

### Backend (FastAPI)

The backend is built with FastAPI and provides REST API endpoints:

**MCP Endpoints:**
- `GET /api/mcp/tools` - List all MCP tools with schemas
- `GET /api/mcp/resources` - List all MCP resources
- `GET /api/mcp/prompts` - List all MCP prompts

**Chat Endpoints:**
- `POST /api/chat` - Send message to LLM with MCP tools
- `WS /ws/chat` - WebSocket for streaming chat responses

**Test Management:**
- `GET /api/tests` - List all test files
- `GET /api/tests/{filename}` - Get test file content
- `POST /api/tests` - Create new test file
- `PUT /api/tests/{filename}` - Update test file
- `DELETE /api/tests/{filename}` - Delete test file
- `POST /api/tests/run` - Run tests from a file

**Configuration:**
- `GET /api/config` - Get current configuration
- `GET /api/models` - List available models per provider

**Health Check:**
- `GET /api/health` - Server and MCP connection status

### Frontend (React)

The frontend is a modern React application built with:

- **Vite**: Fast build tool and dev server
- **TailwindCSS**: Utility-first CSS framework
- **Monaco Editor**: Code editor for YAML editing
- **React Router**: Client-side routing
- **Lucide React**: Beautiful icon set

#### UI Sections

1. **MCP Explorer** (`/`)
   - Browse tools, resources, and prompts
   - Collapsible tool schemas
   - Parameter details with types and requirements
   - Copy schemas to clipboard
   - Filter and search capabilities

2. **Chat Interface** (`/chat`)
   - Interactive chat with LLM
   - Real-time streaming responses
   - Tool call visualization
   - Token usage and cost tracking
   - Model and provider selection

3. **Test Manager** (`/tests`)
   - File browser for YAML test files
   - Monaco editor with syntax highlighting
   - Create, edit, delete test files
   - Run tests with visual results
   - Test result history and statistics

4. **Configuration** (`/config`)
   - View all configuration settings
   - See configuration sources
   - Masked sensitive values
   - Help text for setup

## API Integration

The UI communicates with the backend through REST APIs and WebSockets:

### REST API Example

```javascript
// List MCP tools
const response = await fetch('/api/mcp/tools')
const tools = await response.json()

// Send chat message
const response = await fetch('/api/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    message: 'Get chart 123',
    model: 'claude-haiku-4-5',
    provider: 'anthropic'
  })
})
const result = await response.json()
```

### WebSocket Example

```javascript
// Streaming chat with WebSocket
const ws = new WebSocket('ws://localhost:8000/ws/chat')

ws.onmessage = (event) => {
  const message = JSON.parse(event.data)

  switch (message.type) {
    case 'start':
      console.log('Processing started')
      break
    case 'token':
      console.log('Token:', message.content)
      break
    case 'tool_call':
      console.log('Tool called:', message.tool_name)
      break
    case 'complete':
      console.log('Complete. Cost:', message.cost)
      break
  }
}

ws.send(JSON.stringify({
  type: 'chat',
  message: 'Your question here',
  model: 'claude-haiku-4-5',
  provider: 'anthropic'
}))
```

## File Structure

```
testmcpy/
  server/
    __init__.py
    api.py              # FastAPI routes and logic
    websocket.py        # WebSocket handlers for streaming
  ui/                   # React application
    src/
      components/       # Reusable UI components
      pages/            # Main page components
        MCPExplorer.jsx
        ChatInterface.jsx
        TestManager.jsx
        Configuration.jsx
      App.jsx           # Main app with routing
      main.jsx          # Entry point
      index.css         # Global styles
    dist/               # Built frontend (generated)
    package.json
    vite.config.js
    tailwind.config.js
```

## Development

### Backend Development

The backend code is in `testmcpy/server/`. It reuses all existing testmcpy functionality:

- `mcp_client.py` for MCP connections
- `llm_integration.py` for LLM providers
- `test_runner.py` for test execution
- `config.py` for configuration

To modify backend:
1. Edit files in `testmcpy/server/`
2. Restart the server to see changes

### Frontend Development

The frontend code is in `testmcpy/ui/src/`.

Development workflow:
```bash
# Start backend in dev mode
testmcpy serve --dev --no-browser

# In another terminal, start frontend dev server
cd testmcpy/ui
npm run dev
```

The frontend dev server runs on port 3000 with hot reload. API calls are proxied to the backend on port 8000.

### Building for Production

```bash
cd testmcpy/ui
npm run build
```

This creates an optimized production build in `testmcpy/ui/dist/`.

## Customization

### Styling

The UI uses TailwindCSS. Colors are defined in `tailwind.config.js`:

```javascript
theme: {
  extend: {
    colors: {
      background: '#0f0f0f',
      surface: '#1a1a1a',
      border: '#333333',
      primary: '#3b82f6',
      'primary-hover': '#2563eb',
    }
  }
}
```

### Adding New Pages

1. Create a new component in `ui/src/pages/`
2. Add route in `App.jsx`:

```jsx
<Route path="/mypage" element={<MyPage />} />
```

3. Add navigation link:

```jsx
const navItems = [
  // ...
  { path: '/mypage', label: 'My Page', icon: MyIcon },
]
```

### Adding New API Endpoints

1. Add endpoint in `server/api.py`:

```python
@app.get("/api/myendpoint")
async def my_endpoint():
    return {"data": "value"}
```

2. Call from frontend:

```javascript
const response = await fetch('/api/myendpoint')
const data = await response.json()
```

## Troubleshooting

### Frontend won't build

- Make sure Node.js is installed: `node --version`
- Install dependencies: `cd testmcpy/ui && npm install`
- Check for errors in build output

### Server won't start

- Install server dependencies: `pip install 'testmcpy[server]'`
- Check if port is already in use
- Verify MCP service is accessible

### API calls fail

- Check backend logs for errors
- Verify MCP_URL is configured correctly
- Ensure API keys are set (for Anthropic/OpenAI)

### WebSocket connection fails

- Check that server is running
- Verify firewall/proxy settings
- Try using `--host 0.0.0.0` if accessing remotely

## Security Considerations

### Production Deployment

If deploying to production:

1. **Use HTTPS**: Configure a reverse proxy (nginx, Caddy)
2. **Set CORS properly**: Update `allow_origins` in `api.py`
3. **Add authentication**: Implement auth middleware
4. **Secure API keys**: Use environment variables, never commit
5. **Limit access**: Use firewall rules or VPN

### Example nginx config

```nginx
server {
    listen 443 ssl;
    server_name testmcpy.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Performance

### Backend Optimization

- FastAPI is async by default
- MCP client connection is reused
- Tool schemas are cached

### Frontend Optimization

- Production build is minified and optimized
- Code splitting for faster initial load
- Monaco editor is lazy loaded

## API Documentation

The server provides interactive API documentation:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Future Enhancements

Potential improvements:

- [ ] WebSocket support for streaming tool execution
- [ ] Test result history and comparison
- [ ] Export test results to PDF/HTML
- [ ] Visual test builder (drag-and-drop)
- [ ] Real-time collaboration features
- [ ] Plugin system for custom evaluators
- [ ] Performance metrics and analytics
- [ ] Dark/light theme toggle
- [ ] Keyboard shortcuts
- [ ] Mobile-responsive design

## Contributing

To contribute to the web server feature:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly (backend and frontend)
5. Submit a pull request

## Support

For issues or questions:

- GitHub Issues: https://github.com/preset-io/testmcpy/issues
- Documentation: https://github.com/preset-io/testmcpy

## License

The web server feature is part of testmcpy and is licensed under Apache-2.0.
