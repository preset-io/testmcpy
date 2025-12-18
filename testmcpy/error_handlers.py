# Global Exception Handlers - Never let the server crash
import asyncio
import traceback

from fastapi import HTTPException
from fastapi.responses import JSONResponse


async def global_exception_handler(request, exc):
    """
    Global exception handler to catch all unhandled exceptions.

    This prevents the server from crashing and returns helpful error messages to the client.
    """
    # Log the full traceback
    print(f"Unhandled exception in {request.method} {request.url.path}:")
    traceback.print_exc()

    # Determine error type and message
    if isinstance(exc, HTTPException):
        # FastAPI HTTP exceptions - pass through
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    elif isinstance(exc, asyncio.TimeoutError):
        return JSONResponse(
            status_code=504,
            content={
                "detail": "Request timed out. The operation took too long to complete.",
                "error_type": "timeout",
                "suggestion": "Try again or check if the MCP service is responding",
            },
        )
    elif "MCPTimeoutError" in str(type(exc).__name__):
        return JSONResponse(
            status_code=504,
            content={
                "detail": str(exc),
                "error_type": "mcp_timeout",
                "suggestion": "The MCP service is not responding quickly enough. Check your connection.",
            },
        )
    elif "MCPConnectionError" in str(type(exc).__name__):
        return JSONResponse(
            status_code=503,
            content={
                "detail": str(exc),
                "error_type": "mcp_connection",
                "suggestion": "Cannot connect to MCP service. Verify the URL and authentication settings.",
            },
        )
    elif "MCPError" in str(type(exc).__name__):
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "error_type": "mcp_error",
                "suggestion": "An error occurred while communicating with the MCP service.",
            },
        )
    else:
        # Unknown error
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"An unexpected error occurred: {str(exc)}",
                "error_type": type(exc).__name__,
                "suggestion": "Please try again. If the problem persists, check the server logs.",
            },
        )
