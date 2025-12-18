"""
MCP Connection Manager.

Handles MCP profile management, connection pooling, and health checks.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from testmcpy.mcp_profiles import MCPProfile, get_profile_config, load_profile
from testmcpy.src.mcp_client import MCPClient


class ConnectionStatus(str, Enum):
    """MCP connection status."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    CONNECTING = "connecting"


@dataclass
class MCPConnection:
    """Represents an active MCP connection."""

    profile_id: str
    mcp_name: str
    client: MCPClient
    status: ConnectionStatus
    error: str | None = None


class MCPManager:
    """
    Manages MCP connections and profiles.

    Provides centralized connection management with:
    - Connection pooling per profile/server
    - Health checking
    - Auth handling (JWT, OAuth, Bearer)
    - Profile discovery
    """

    def __init__(self):
        """Initialize MCP manager."""
        self._connections: dict[str, MCPConnection] = {}  # Key: "{profile_id}:{mcp_name}"

    def _get_connection_key(self, profile_id: str, mcp_name: str) -> str:
        """Generate cache key for a connection."""
        return f"{profile_id}:{mcp_name}"

    def list_profiles(self) -> list[MCPProfile]:
        """
        List all available MCP profiles.

        Returns:
            List of MCPProfile objects with their configurations.
        """
        profile_config = get_profile_config()
        profiles = []

        for profile_id in profile_config.list_profiles():
            profile = profile_config.get_profile(profile_id)
            if profile:
                profiles.append(profile)

        return profiles

    async def connect_profile(self, profile_id: str, mcp_name: str | None = None) -> MCPClient:
        """
        Connect to an MCP server in a profile.

        Args:
            profile_id: The profile ID to connect to
            mcp_name: Optional specific MCP server name. If None, connects to first MCP in profile.

        Returns:
            Connected MCPClient instance

        Raises:
            ValueError: If profile or MCP server not found
            Exception: If connection fails
        """
        # Load profile
        profile = load_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile '{profile_id}' not found in .mcp_services.yaml")

        # Handle empty MCP list
        if not profile.mcps:
            raise ValueError(f"Profile '{profile_id}' has no MCP servers configured")

        # Find the MCP server
        if mcp_name is None:
            # Use default MCP server (marked default or first one)
            mcp_server = None
            for server in profile.mcps:
                if server.default:
                    mcp_server = server
                    break
            if not mcp_server:
                mcp_server = profile.mcps[0]
        else:
            # Find specific MCP server
            mcp_server = None
            for server in profile.mcps:
                if server.name == mcp_name:
                    mcp_server = server
                    break

            if not mcp_server:
                raise ValueError(f"MCP server '{mcp_name}' not found in profile '{profile_id}'")

        # Check if already connected
        conn_key = self._get_connection_key(profile_id, mcp_server.name)
        if conn_key in self._connections:
            connection = self._connections[conn_key]
            if connection.status == ConnectionStatus.CONNECTED:
                return connection.client

        # Create new connection
        try:
            auth_dict = mcp_server.auth.to_dict()
            client = MCPClient(mcp_server.mcp_url, auth=auth_dict)

            # Mark as connecting
            self._connections[conn_key] = MCPConnection(
                profile_id=profile_id,
                mcp_name=mcp_server.name,
                client=client,
                status=ConnectionStatus.CONNECTING,
            )

            # Initialize connection
            await client.initialize()

            # Update status
            self._connections[conn_key].status = ConnectionStatus.CONNECTED
            self._connections[conn_key].error = None

            return client

        except Exception as e:
            # Update error status
            if conn_key in self._connections:
                self._connections[conn_key].status = ConnectionStatus.ERROR
                self._connections[conn_key].error = str(e)

            raise Exception(f"Failed to connect to MCP '{mcp_server.name}': {e}")

    async def disconnect_profile(self, profile_id: str, mcp_name: str | None = None):
        """
        Disconnect from MCP server(s) in a profile.

        Args:
            profile_id: The profile ID
            mcp_name: Optional specific MCP server name. If None, disconnects all MCPs in profile.
        """
        if mcp_name:
            # Disconnect specific MCP
            conn_key = self._get_connection_key(profile_id, mcp_name)
            if conn_key in self._connections:
                connection = self._connections[conn_key]
                try:
                    await connection.client.close()
                except Exception as e:
                    print(f"Warning: Error closing connection '{conn_key}': {e}")
                finally:
                    connection.status = ConnectionStatus.DISCONNECTED
                    del self._connections[conn_key]
        else:
            # Disconnect all MCPs for this profile
            keys_to_remove = [
                key for key in self._connections.keys() if key.startswith(f"{profile_id}:")
            ]

            for key in keys_to_remove:
                connection = self._connections[key]
                try:
                    await connection.client.close()
                except Exception as e:
                    print(f"Warning: Error closing connection '{key}': {e}")
                finally:
                    connection.status = ConnectionStatus.DISCONNECTED
                    del self._connections[key]

    def get_connection_status(self, profile_id: str, mcp_name: str) -> dict[str, Any]:
        """
        Get connection status for a specific MCP server.

        Args:
            profile_id: The profile ID
            mcp_name: The MCP server name

        Returns:
            Dictionary with status information:
            - status: ConnectionStatus enum value
            - error: Error message if status is ERROR
            - connected: Boolean indicating if connected
        """
        conn_key = self._get_connection_key(profile_id, mcp_name)

        if conn_key not in self._connections:
            return {
                "status": ConnectionStatus.DISCONNECTED,
                "error": None,
                "connected": False,
            }

        connection = self._connections[conn_key]
        return {
            "status": connection.status,
            "error": connection.error,
            "connected": connection.status == ConnectionStatus.CONNECTED,
        }

    def get_default_profile(self) -> str | None:
        """
        Get the default profile ID.

        Returns:
            Default profile ID or None if not configured.
        """
        profile_config = get_profile_config()
        return profile_config.default_profile

    async def get_client(self, profile_id: str, mcp_name: str) -> MCPClient | None:
        """
        Get an existing connected client or None.

        Args:
            profile_id: The profile ID
            mcp_name: The MCP server name

        Returns:
            MCPClient if connected, None otherwise
        """
        conn_key = self._get_connection_key(profile_id, mcp_name)
        connection = self._connections.get(conn_key)

        if connection and connection.status == ConnectionStatus.CONNECTED:
            return connection.client

        return None

    async def get_or_connect(self, profile_id: str, mcp_name: str | None = None) -> MCPClient:
        """
        Get existing client or create new connection.

        Args:
            profile_id: The profile ID
            mcp_name: Optional specific MCP server name

        Returns:
            Connected MCPClient instance
        """
        # If no mcp_name provided, load profile and use default MCP
        if mcp_name is None:
            profile = load_profile(profile_id)
            if not profile or not profile.mcps:
                raise ValueError(f"Profile '{profile_id}' has no MCP servers")
            # Get default MCP server (marked default or first one)
            default_mcp = None
            for mcp in profile.mcps:
                if mcp.default:
                    default_mcp = mcp
                    break
            if not default_mcp:
                default_mcp = profile.mcps[0]
            mcp_name = default_mcp.name

        # Try to get existing client
        client = await self.get_client(profile_id, mcp_name)
        if client:
            return client

        # Connect if not exists
        return await self.connect_profile(profile_id, mcp_name)

    async def health_check(self, profile_id: str, mcp_name: str) -> dict[str, Any]:
        """
        Perform health check on an MCP connection.

        Args:
            profile_id: The profile ID
            mcp_name: The MCP server name

        Returns:
            Dictionary with health check results:
            - healthy: Boolean
            - response_time_ms: Response time in milliseconds
            - error: Error message if unhealthy
        """
        import time

        try:
            client = await self.get_or_connect(profile_id, mcp_name)

            start_time = time.time()
            await client.list_tools()
            response_time = (time.time() - start_time) * 1000

            return {
                "healthy": True,
                "response_time_ms": round(response_time, 2),
                "error": None,
            }

        except Exception as e:
            return {
                "healthy": False,
                "response_time_ms": None,
                "error": str(e),
            }

    async def close_all(self):
        """Close all MCP connections."""
        for conn_key, connection in list(self._connections.items()):
            try:
                await connection.client.close()
            except Exception as e:
                print(f"Warning: Error closing connection '{conn_key}': {e}")
            finally:
                connection.status = ConnectionStatus.DISCONNECTED

        self._connections.clear()
