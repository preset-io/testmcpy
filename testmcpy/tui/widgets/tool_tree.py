"""
Tool tree widget for TUI explorer.

Provides a hierarchical tree view of MCP tools organized by categories.
"""

from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from testmcpy.src.mcp_client import MCPTool


class ToolTree(Tree):
    """Tree widget for displaying MCP tools organized by categories."""

    def __init__(self, *args, **kwargs):
        """Initialize the tool tree."""
        super().__init__("MCP Tools", *args, **kwargs)
        self.tools_by_category: dict[str, list[MCPTool]] = {}
        self.tool_nodes: dict[str, TreeNode] = {}
        self.show_root = False

    def load_tools(self, categorized_tools: dict[str, list[MCPTool]]):
        """
        Load tools into the tree.

        Args:
            categorized_tools: Dictionary mapping category names to lists of tools
        """
        self.tools_by_category = categorized_tools
        self.tool_nodes.clear()

        # Clear existing tree
        self.clear()

        # Add categories and tools
        for category, tools in categorized_tools.items():
            # Add category node with count
            category_label = f"{category} [{len(tools)}]"
            category_node = self.root.add(category_label, expand=True)

            # Add tools under category
            for tool in tools:
                tool_node = category_node.add_leaf(tool.name)
                # Store reference to tool for later retrieval
                tool_node.data = tool
                self.tool_nodes[tool.name] = tool_node

    def get_selected_tool(self) -> MCPTool | None:
        """
        Get the currently selected tool.

        Returns:
            MCPTool object if a tool is selected, None otherwise
        """
        if not self.cursor_node:
            return None

        # Check if selected node has tool data
        if hasattr(self.cursor_node, "data") and isinstance(self.cursor_node.data, MCPTool):
            return self.cursor_node.data

        return None

    def filter_tools(self, search_term: str):
        """
        Filter tools based on search term.

        Args:
            search_term: Search string to filter by
        """
        if not search_term:
            # Reload all tools if search is cleared
            self.load_tools(self.tools_by_category)
            return

        search_lower = search_term.lower()

        # Filter tools
        filtered_categories = {}
        for category, tools in self.tools_by_category.items():
            matching_tools = [
                tool
                for tool in tools
                if search_lower in tool.name.lower() or search_lower in tool.description.lower()
            ]
            if matching_tools:
                filtered_categories[category] = matching_tools

        # Reload tree with filtered tools
        self.clear()

        if not filtered_categories:
            # Show "no results" message
            self.root.add_leaf("No matching tools found")
            return

        # Load filtered results
        for category, tools in filtered_categories.items():
            category_label = f"{category} [{len(tools)}]"
            category_node = self.root.add(category_label, expand=True)

            for tool in tools:
                tool_node = category_node.add_leaf(tool.name)
                tool_node.data = tool
                self.tool_nodes[tool.name] = tool_node

    def get_all_tools(self) -> list[MCPTool]:
        """
        Get all tools across all categories.

        Returns:
            List of all MCPTool objects
        """
        all_tools = []
        for tools in self.tools_by_category.values():
            all_tools.extend(tools)
        return all_tools

    def select_tool_by_name(self, tool_name: str):
        """
        Select a tool by its name.

        Args:
            tool_name: Name of the tool to select
        """
        if tool_name in self.tool_nodes:
            node = self.tool_nodes[tool_name]
            self.select_node(node)
            self.scroll_to_node(node)

    def get_tool_count(self) -> int:
        """
        Get total count of tools.

        Returns:
            Total number of tools
        """
        return sum(len(tools) for tools in self.tools_by_category.values())
