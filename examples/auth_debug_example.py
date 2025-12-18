"""
Example demonstrating OAuth/JWT authentication debugging with AuthDebugger.

This example shows how to use the new debug parameter in authentication methods
to get detailed, step-by-step visibility into the authentication flow.
"""

import asyncio
from testmcpy.src.mcp_client import MCPClient


async def example_oauth_with_debug():
    """Example: OAuth authentication with debugging enabled."""
    print("\n" + "=" * 70)
    print("Example 1: OAuth Client Credentials Flow with Debug Logging")
    print("=" * 70 + "\n")

    auth = {
        "type": "oauth",
        "client_id": "your-client-id",
        "client_secret": "your-client-secret",
        "token_url": "https://auth.example.com/oauth/token",
        "scopes": ["read", "write"],
    }

    # Create client with auth config
    client = MCPClient(base_url="http://localhost:5008/mcp", auth=auth)

    # The debug parameter can be passed when calling _fetch_oauth_token directly
    # In production, you would pass debug through the auth config or as a parameter
    try:
        # This will show detailed debug output with Rich console formatting
        token = await client._fetch_oauth_token(
            client_id=auth["client_id"],
            client_secret=auth["client_secret"],
            token_url=auth["token_url"],
            scopes=auth["scopes"],
            debug=True,  # Enable debug logging
        )
        print(f"\nToken fetched: {token[:20]}...")
    except Exception as e:
        print(f"\nError: {e}")


async def example_jwt_with_debug():
    """Example: JWT token fetch with debugging enabled."""
    print("\n" + "=" * 70)
    print("Example 2: JWT Dynamic Token Fetch with Debug Logging")
    print("=" * 70 + "\n")

    auth = {
        "type": "jwt",
        "api_url": "https://api.example.com/auth/token",
        "api_token": "your-api-token",
        "api_secret": "your-api-secret",
    }

    client = MCPClient(base_url="http://localhost:5008/mcp", auth=auth)

    try:
        # This will show detailed debug output with Rich console formatting
        token = await client._fetch_jwt_token(
            api_url=auth["api_url"],
            api_token=auth["api_token"],
            api_secret=auth["api_secret"],
            debug=True,  # Enable debug logging
        )
        print(f"\nToken fetched: {token[:20]}...")
    except Exception as e:
        print(f"\nError: {e}")


async def example_without_debug():
    """Example: Standard authentication without debug logging."""
    print("\n" + "=" * 70)
    print("Example 3: OAuth without Debug (Backward Compatible)")
    print("=" * 70 + "\n")

    auth = {
        "type": "oauth",
        "client_id": "your-client-id",
        "client_secret": "your-client-secret",
        "token_url": "https://auth.example.com/oauth/token",
    }

    client = MCPClient(base_url="http://localhost:5008/mcp", auth=auth)

    try:
        # Default behavior - no debug output (debug=False by default)
        token = await client._fetch_oauth_token(
            client_id=auth["client_id"],
            client_secret=auth["client_secret"],
            token_url=auth["token_url"],
            # debug parameter not specified - defaults to False
        )
        print(f"Token fetched: {token[:20]}...")
    except Exception as e:
        print(f"Error: {e}")


async def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print("Authentication Debugging Examples")
    print("=" * 70)
    print("\nThese examples demonstrate the new debug parameter added to")
    print("OAuth and JWT authentication methods in Phase 1.2 of PROJECT_AUTH.md")
    print("\nNote: These examples will fail without valid credentials.")
    print("Replace the placeholder values with real credentials to test.")

    # Example 1: OAuth with debug
    # await example_oauth_with_debug()

    # Example 2: JWT with debug
    # await example_jwt_with_debug()

    # Example 3: OAuth without debug (backward compatible)
    # await example_without_debug()

    print("\n" + "=" * 70)
    print("Examples completed!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    print("\n⚠️  To run these examples, uncomment the example calls in main()")
    print("    and replace placeholder credentials with real values.\n")
    # asyncio.run(main())
