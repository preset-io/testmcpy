import asyncio
import sys
from testmcpy.src.mcp_client import MCPClient, MCPToolCall

async def main():
    # Initialize client with sandbox profile settings
    client = MCPClient(
        base_url="https://66d22a6f.us1a.app-sdx.preset.io/mcp",
        auth={
            "type": "jwt",
            "api_url": "https://api.app-sdx.preset.io/v1/auth/",
            "api_token": sys.argv[1] if len(sys.argv) > 1 else None,
            "api_secret": sys.argv[2] if len(sys.argv) > 2 else None,
        }
    )
    
    try:
        # Initialize connection
        await client.initialize()
        
        # Call list_charts tool
        tool_call = MCPToolCall(
            name="list_charts",
            arguments={"request": {}},
            id="list_charts_1"
        )
        
        result = await client.call_tool(tool_call, timeout=30.0)
        
        if result.is_error:
            print(f"Error: {result.error_message}")
        else:
            print(result.content)
            
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
