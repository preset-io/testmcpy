"""
API key authentication middleware for testmcpy server.

When TESTMCPY_API_KEY is set, write endpoints (POST/PUT/DELETE) on /api/*
require Authorization: Bearer <key>. GET requests and non-API routes are open.

When TESTMCPY_API_KEY is not set, no authentication is required (local dev mode).
"""

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# HTTP methods that require authentication
WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces API key auth on write endpoints."""

    async def dispatch(self, request, call_next):
        api_key = os.environ.get("TESTMCPY_API_KEY")

        # No API key configured — skip auth entirely (local dev mode)
        if not api_key:
            return await call_next(request)

        # Only protect /api/* write endpoints
        path = request.url.path
        method = request.method

        if path.startswith("/api/") and method in WRITE_METHODS:
            auth_header = request.headers.get("authorization", "")

            if not auth_header.startswith("Bearer "):
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": "Missing or invalid Authorization header. Expected: Bearer <api_key>"
                    },
                )

            provided_key = auth_header[len("Bearer ") :]
            if provided_key != api_key:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Invalid API key"},
                )

        return await call_next(request)
