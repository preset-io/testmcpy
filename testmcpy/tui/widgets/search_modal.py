"""
Global search modal for finding tools, tests, and content.
"""

from dataclasses import dataclass
from typing import Any, Literal

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static


@dataclass
class SearchResult:
    """A search result item."""

    type: Literal["tool", "test", "chat", "config"]
    title: str
    subtitle: str
    data: Any
    score: float = 1.0  # Relevance score (0-1)


class SearchResultItem(ListItem):
    """A single search result in the list."""

    DEFAULT_CSS = """
    SearchResultItem {
        height: auto;
        padding: 1;
    }

    SearchResultItem .result-type {
        color: $primary;
        bold: true;
    }

    SearchResultItem .result-title {
        color: $text;
    }

    SearchResultItem .result-subtitle {
        color: $text-muted;
    }

    SearchResultItem:hover {
        background: $surface;
    }
    """

    def __init__(self, result: SearchResult):
        super().__init__()
        self.result = result

    def compose(self) -> ComposeResult:
        """Compose the search result item."""
        # Type indicator
        type_icon = {
            "tool": "🔧",
            "test": "🧪",
            "chat": "💬",
            "config": "⚙️",
        }.get(self.result.type, "📄")

        yield Label(f"{type_icon} {self.result.type.upper()}", classes="result-type")
        yield Label(self.result.title, classes="result-title")
        if self.result.subtitle:
            yield Label(self.result.subtitle, classes="result-subtitle")


class GlobalSearchModal(ModalScreen):
    """Global search modal for finding anything in the app."""

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel", priority=True),
        Binding("ctrl+c", "dismiss", "Cancel", priority=True),
        Binding("enter", "select", "Select", priority=True),
        Binding("down", "next_result", "Next", priority=True),
        Binding("up", "prev_result", "Previous", priority=True),
    ]

    DEFAULT_CSS = """
    GlobalSearchModal {
        align: center top;
    }

    #search_dialog {
        width: 80;
        max-width: 100;
        height: 70%;
        margin-top: 5;
        border: thick $primary;
        background: $background;
    }

    #search_input_container {
        dock: top;
        height: auto;
        background: $surface;
        padding: 1;
    }

    #search_input {
        width: 100%;
    }

    #search_results {
        height: 100%;
    }

    #search_help {
        dock: bottom;
        height: auto;
        background: $surface;
        padding: 1;
        color: $text-muted;
        text-align: center;
    }

    #no_results {
        height: 100%;
        align: center middle;
        color: $dim;
    }
    """

    def __init__(self):
        super().__init__()
        self.results: list[SearchResult] = []

    def compose(self) -> ComposeResult:
        """Compose the search modal."""
        with Vertical(id="search_dialog"):
            with Container(id="search_input_container"):
                yield Label("🔍 Global Search")
                yield Input(
                    placeholder="Search tools, tests, chat history, config...",
                    id="search_input",
                )

            with VerticalScroll(id="search_results"):
                yield ListView(id="results_list")

            yield Static(
                "↑↓ Navigate  •  Enter Select  •  Esc Cancel",
                id="search_help",
            )

    def on_mount(self) -> None:
        """Focus the search input when modal opens."""
        self.query_one("#search_input", Input).focus()

    @on(Input.Changed, "#search_input")
    @work
    async def search(self, event: Input.Changed) -> None:
        """Perform search as user types."""
        query = event.value.strip().lower()

        if not query:
            # Clear results
            results_list = self.query_one("#results_list", ListView)
            results_list.clear()
            self.results = []
            return

        # Perform fuzzy search
        self.results = await self._perform_search(query)

        # Update results list
        results_list = self.query_one("#results_list", ListView)
        results_list.clear()

        if not self.results:
            results_list.append(
                ListItem(Label("No results found", id="no_results"))
            )
        else:
            for result in self.results:
                results_list.append(SearchResultItem(result))

    async def _perform_search(self, query: str) -> list[SearchResult]:
        """
        Perform fuzzy search across all searchable content.

        This is a mock implementation - in a real app, this would:
        1. Search MCP tools from connected services
        2. Search test files in tests/ directory
        3. Search chat history if available
        4. Search configuration options
        """
        results = []

        # Mock results for demonstration
        # TODO: Replace with actual search implementation

        # Search tools
        mock_tools = [
            ("generate_chart", "Create and save a chart in Superset"),
            ("create_dashboard", "Create a new dashboard"),
            ("execute_sql", "Execute SQL query"),
            ("list_datasets", "List available datasets"),
        ]

        for tool_name, tool_desc in mock_tools:
            if self._fuzzy_match(query, tool_name) or self._fuzzy_match(query, tool_desc):
                score = self._calculate_score(query, tool_name, tool_desc)
                results.append(
                    SearchResult(
                        type="tool",
                        title=tool_name,
                        subtitle=tool_desc,
                        data={"tool_name": tool_name},
                        score=score,
                    )
                )

        # Search tests
        mock_tests = [
            ("test_chart_creation.yaml", "Tests chart creation workflow"),
            ("test_dashboard_query.yaml", "Tests dashboard querying"),
            ("test_dataset_validation.yaml", "Validates dataset operations"),
        ]

        for test_name, test_desc in mock_tests:
            if self._fuzzy_match(query, test_name) or self._fuzzy_match(query, test_desc):
                score = self._calculate_score(query, test_name, test_desc)
                results.append(
                    SearchResult(
                        type="test",
                        title=test_name,
                        subtitle=test_desc,
                        data={"test_file": test_name},
                        score=score,
                    )
                )

        # Search config options
        config_items = [
            ("LLM Provider", "Configure default LLM provider (Anthropic, OpenAI, Ollama)"),
            ("API Keys", "Manage API keys for LLM providers"),
            ("MCP Profiles", "Manage MCP service profiles"),
            ("Theme", "Change color scheme"),
        ]

        for config_name, config_desc in config_items:
            if self._fuzzy_match(query, config_name) or self._fuzzy_match(query, config_desc):
                score = self._calculate_score(query, config_name, config_desc)
                results.append(
                    SearchResult(
                        type="config",
                        title=config_name,
                        subtitle=config_desc,
                        data={"config_section": config_name},
                        score=score,
                    )
                )

        # Sort by relevance score
        results.sort(key=lambda r: r.score, reverse=True)

        return results[:20]  # Limit to top 20 results

    def _fuzzy_match(self, query: str, text: str) -> bool:
        """Simple fuzzy matching."""
        query = query.lower()
        text = text.lower()

        # Exact substring match
        if query in text:
            return True

        # Check if all characters in query appear in order in text
        query_idx = 0
        for char in text:
            if query_idx < len(query) and char == query[query_idx]:
                query_idx += 1

        return query_idx == len(query)

    def _calculate_score(self, query: str, title: str, subtitle: str) -> float:
        """Calculate relevance score for a result."""
        query = query.lower()
        title = title.lower()
        subtitle = subtitle.lower()

        score = 0.0

        # Exact title match
        if query == title:
            score += 1.0
        # Title starts with query
        elif title.startswith(query):
            score += 0.8
        # Query in title
        elif query in title:
            score += 0.6
        # Query in subtitle
        elif query in subtitle:
            score += 0.4
        # Fuzzy match
        else:
            score += 0.2

        return score

    def action_select(self) -> None:
        """Select the highlighted result."""
        results_list = self.query_one("#results_list", ListView)
        selected_item = results_list.highlighted_child

        if isinstance(selected_item, SearchResultItem):
            result = selected_item.result
            # Dismiss modal and pass result to callback
            self.dismiss(result)
        else:
            self.dismiss(None)

    def action_next_result(self) -> None:
        """Move to next result."""
        results_list = self.query_one("#results_list", ListView)
        results_list.action_cursor_down()

    def action_prev_result(self) -> None:
        """Move to previous result."""
        results_list = self.query_one("#results_list", ListView)
        results_list.action_cursor_up()

    def action_dismiss(self) -> None:
        """Dismiss the search modal."""
        self.dismiss(None)
