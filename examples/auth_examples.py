"""
Examples of using MCPClient with different authentication types.

This demonstrates how to use the auth parameter to pass authentication
configuration directly to the MCPClient constructor.
"""

import asyncio
from testmcpy.src.mcp_client import MCPClient


async def example_bearer_auth():
    """Example: Using bearer token authentication."""
    auth = {
        "type": "bearer",
        "token": "your-bearer-token-here"
    }

    async with MCPClient(base_url="http://localhost:5008/mcp", auth=auth) as client:
        tools = await client.list_tools()
        print(f"Found {len(tools)} tools")


async def example_jwt_auth():
    """Example: Using dynamic JWT authentication."""
    auth = {
        "type": "jwt",
        "api_url": "https://api.example.com/auth/token",
        "api_token": "your-api-token",
        "api_secret": "your-api-secret"
    }

    async with MCPClient(base_url="http://localhost:5008/mcp", auth=auth) as client:
        tools = await client.list_tools()
        print(f"Found {len(tools)} tools")


async def example_oauth_auth():
    """Example: Using OAuth client credentials authentication."""
    auth = {
        "type": "oauth",
        "client_id": "your-client-id",
        "client_secret": "your-client-secret",
        "token_url": "https://oauth.example.com/token",
        "scopes": ["read", "write"]  # Optional
    }

    async with MCPClient(base_url="http://localhost:5008/mcp", auth=auth) as client:
        tools = await client.list_tools()
        print(f"Found {len(tools)} tools")


async def example_no_auth():
    """Example: Explicitly no authentication."""
    auth = {
        "type": "none"
    }

    async with MCPClient(base_url="http://localhost:5008/mcp", auth=auth) as client:
        tools = await client.list_tools()
        print(f"Found {len(tools)} tools")


async def example_config_fallback():
    """Example: Fall back to config-based authentication."""
    # When auth parameter is not provided, it falls back to config
    async with MCPClient(base_url="http://localhost:5008/mcp") as client:
        tools = await client.list_tools()
        print(f"Found {len(tools)} tools")


async def example_from_profile():
    """Example: Load authentication from MCP profile."""
    from testmcpy.mcp_profiles import load_profile

    # Load profile
    profile = load_profile("production")  # or any profile ID

    if profile and profile.mcps:
        # Use first MCP from profile
        mcp = profile.mcps[0]

        # Convert AuthConfig to dict for MCPClient (using helper method)
        auth = mcp.auth.to_dict()

        async with MCPClient(base_url=mcp.mcp_url, auth=auth) as client:
            tools = await client.list_tools()
            print(f"Found {len(tools)} tools from profile")


if __name__ == "__main__":
    # Run example (choose one)
    # asyncio.run(example_bearer_auth())
    # asyncio.run(example_jwt_auth())
    # asyncio.run(example_oauth_auth())
    # asyncio.run(example_no_auth())
    asyncio.run(example_config_fallback())
