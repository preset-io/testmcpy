"""
Tool Discovery Service.

Discovers and caches MCP tools, resources, and prompts across multiple profiles.
"""

from dataclasses import dataclass
from typing import Any

from testmcpy.src.mcp_client import MCPTool


@dataclass
class Tool:
    """Represents a discovered MCP tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    profile_id: str
    mcp_name: str

    @classmethod
    def from_mcp_tool(cls, mcp_tool: MCPTool, profile_id: str, mcp_name: str) -> "Tool":
        """Create Tool from MCPTool."""
        return cls(
            name=mcp_tool.name,
            description=mcp_tool.description,
            input_schema=mcp_tool.input_schema,
            profile_id=profile_id,
            mcp_name=mcp_name,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "profile_id": self.profile_id,
            "mcp_name": self.mcp_name,
        }


@dataclass
class Resource:
    """Represents a discovered MCP resource."""

    name: str
    description: str
    uri: str
    profile_id: str
    mcp_name: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "uri": self.uri,
            "profile_id": self.profile_id,
            "mcp_name": self.mcp_name,
        }


@dataclass
class Prompt:
    """Represents a discovered MCP prompt."""

    name: str
    description: str
    profile_id: str
    mcp_name: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "profile_id": self.profile_id,
            "mcp_name": self.mcp_name,
        }


class ToolDiscovery:
    """
    Discovers and manages MCP tools, resources, and prompts.

    Features:
    - Tool discovery across multiple MCP servers
    - Caching for performance
    - Resource and prompt discovery
    - Profile-aware discovery
    """

    def __init__(self, mcp_manager):
        """
        Initialize tool discovery.

        Args:
            mcp_manager: MCPManager instance for connection management
        """
        from testmcpy.core.mcp_manager import MCPManager

        self.mcp_manager: MCPManager = mcp_manager
        self._tools_cache: dict[str, list[Tool]] = {}  # Key: "{profile_id}:{mcp_name}"
        self._resources_cache: dict[str, list[Resource]] = {}
        self._prompts_cache: dict[str, list[Prompt]] = {}

    def _get_cache_key(self, profile_id: str, mcp_name: str) -> str:
        """Generate cache key."""
        return f"{profile_id}:{mcp_name}"

    async def list_tools(
        self, profile_id: str, mcp_name: str | None = None, force_refresh: bool = False
    ) -> list[Tool]:
        """
        List all available tools from MCP server(s).

        Args:
            profile_id: The profile ID
            mcp_name: Optional specific MCP server name. If None, lists from all MCPs in profile.
            force_refresh: Force refresh from MCP service

        Returns:
            List of Tool objects
        """
        from testmcpy.mcp_profiles import load_profile

        profile = load_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile '{profile_id}' not found")

        if not profile.mcps:
            return []

        # Determine which MCP servers to query
        if mcp_name:
            mcp_servers = [s for s in profile.mcps if s.name == mcp_name]
            if not mcp_servers:
                raise ValueError(f"MCP server '{mcp_name}' not found in profile '{profile_id}'")
        else:
            mcp_servers = profile.mcps

        # Collect tools from all requested MCP servers
        all_tools = []

        for mcp_server in mcp_servers:
            cache_key = self._get_cache_key(profile_id, mcp_server.name)

            # Check cache
            if not force_refresh and cache_key in self._tools_cache:
                all_tools.extend(self._tools_cache[cache_key])
                continue

            # Fetch from MCP
            try:
                client = await self.mcp_manager.get_or_connect(profile_id, mcp_server.name)
                mcp_tools = await client.list_tools(force_refresh=force_refresh)

                # Convert to Tool objects
                tools = [Tool.from_mcp_tool(t, profile_id, mcp_server.name) for t in mcp_tools]

                # Update cache
                self._tools_cache[cache_key] = tools
                all_tools.extend(tools)

            except Exception as e:
                print(f"Warning: Failed to list tools from '{mcp_server.name}': {e}")
                continue

        return all_tools

    async def get_tool(self, profile_id: str, tool_name: str) -> Tool | None:
        """
        Get a specific tool by name.

        Args:
            profile_id: The profile ID
            tool_name: The tool name to find

        Returns:
            Tool object if found, None otherwise
        """
        # List all tools from this profile
        tools = await self.list_tools(profile_id)

        # Find the tool
        for tool in tools:
            if tool.name == tool_name:
                return tool

        return None

    async def list_resources(
        self, profile_id: str, mcp_name: str | None = None, force_refresh: bool = False
    ) -> list[Resource]:
        """
        List all available resources from MCP server(s).

        Args:
            profile_id: The profile ID
            mcp_name: Optional specific MCP server name. If None, lists from all MCPs in profile.
            force_refresh: Force refresh from MCP service

        Returns:
            List of Resource objects
        """
        from testmcpy.mcp_profiles import load_profile

        profile = load_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile '{profile_id}' not found")

        if not profile.mcps:
            return []

        # Determine which MCP servers to query
        if mcp_name:
            mcp_servers = [s for s in profile.mcps if s.name == mcp_name]
            if not mcp_servers:
                raise ValueError(f"MCP server '{mcp_name}' not found in profile '{profile_id}'")
        else:
            mcp_servers = profile.mcps

        # Collect resources from all requested MCP servers
        all_resources = []

        for mcp_server in mcp_servers:
            cache_key = self._get_cache_key(profile_id, mcp_server.name)

            # Check cache
            if not force_refresh and cache_key in self._resources_cache:
                all_resources.extend(self._resources_cache[cache_key])
                continue

            # Fetch from MCP
            try:
                client = await self.mcp_manager.get_or_connect(profile_id, mcp_server.name)
                mcp_resources = await client.list_resources()

                # Convert to Resource objects
                resources = [
                    Resource(
                        name=r.get("name", ""),
                        description=r.get("description", ""),
                        uri=r.get("uri", ""),
                        profile_id=profile_id,
                        mcp_name=mcp_server.name,
                    )
                    for r in mcp_resources
                ]

                # Update cache
                self._resources_cache[cache_key] = resources
                all_resources.extend(resources)

            except Exception as e:
                print(f"Warning: Failed to list resources from '{mcp_server.name}': {e}")
                continue

        return all_resources

    async def list_prompts(
        self, profile_id: str, mcp_name: str | None = None, force_refresh: bool = False
    ) -> list[Prompt]:
        """
        List all available prompts from MCP server(s).

        Args:
            profile_id: The profile ID
            mcp_name: Optional specific MCP server name. If None, lists from all MCPs in profile.
            force_refresh: Force refresh from MCP service

        Returns:
            List of Prompt objects
        """
        from testmcpy.mcp_profiles import load_profile

        profile = load_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile '{profile_id}' not found")

        if not profile.mcps:
            return []

        # Determine which MCP servers to query
        if mcp_name:
            mcp_servers = [s for s in profile.mcps if s.name == mcp_name]
            if not mcp_servers:
                raise ValueError(f"MCP server '{mcp_name}' not found in profile '{profile_id}'")
        else:
            mcp_servers = profile.mcps

        # Collect prompts from all requested MCP servers
        all_prompts = []

        for mcp_server in mcp_servers:
            cache_key = self._get_cache_key(profile_id, mcp_server.name)

            # Check cache
            if not force_refresh and cache_key in self._prompts_cache:
                all_prompts.extend(self._prompts_cache[cache_key])
                continue

            # Fetch from MCP
            try:
                client = await self.mcp_manager.get_or_connect(profile_id, mcp_server.name)
                mcp_prompts = await client.list_prompts()

                # Convert to Prompt objects
                prompts = [
                    Prompt(
                        name=p.get("name", ""),
                        description=p.get("description", ""),
                        profile_id=profile_id,
                        mcp_name=mcp_server.name,
                    )
                    for p in mcp_prompts
                ]

                # Update cache
                self._prompts_cache[cache_key] = prompts
                all_prompts.extend(prompts)

            except Exception as e:
                print(f"Warning: Failed to list prompts from '{mcp_server.name}': {e}")
                continue

        return all_prompts

    def clear_cache(self, profile_id: str | None = None, mcp_name: str | None = None):
        """
        Clear cached tools, resources, and prompts.

        Args:
            profile_id: Optional profile ID. If None, clears all caches.
            mcp_name: Optional MCP name. Only used if profile_id is provided.
        """
        if profile_id is None:
            # Clear all caches
            self._tools_cache.clear()
            self._resources_cache.clear()
            self._prompts_cache.clear()
        elif mcp_name is None:
            # Clear all caches for a profile
            keys_to_remove = [
                key for key in self._tools_cache.keys() if key.startswith(f"{profile_id}:")
            ]
            for key in keys_to_remove:
                self._tools_cache.pop(key, None)
                self._resources_cache.pop(key, None)
                self._prompts_cache.pop(key, None)
        else:
            # Clear cache for specific MCP
            cache_key = self._get_cache_key(profile_id, mcp_name)
            self._tools_cache.pop(cache_key, None)
            self._resources_cache.pop(cache_key, None)
            self._prompts_cache.pop(cache_key, None)
