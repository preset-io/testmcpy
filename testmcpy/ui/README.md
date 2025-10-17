# testmcpy Web UI

Beautiful React-based web interface for testmcpy.

## Features

- **MCP Explorer**: Browse MCP tools, resources, and prompts with their schemas
- **Chat Interface**: Interactive chat with LLM using MCP tools
- **Test Manager**: Create, edit, run, and manage YAML test files
- **Configuration**: View current testmcpy configuration

## Development

```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build
```

## Tech Stack

- React 18
- Vite
- TailwindCSS
- React Router
- Monaco Editor (for YAML editing)
- Lucide React (icons)

## Usage

The UI is automatically served by the testmcpy server. Just run:

```bash
testmcpy serve
```

This will build the frontend (if needed) and start the server at http://localhost:8000.
