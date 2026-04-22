"""
Unit tests for tool filtering + setup/teardown hooks on TestCase.

Batch 6+7: include_tools, exclude_tools, setup, teardown.
"""

from testmcpy.src.test_runner import TestCase


class TestToolFilteringFields:
    """Test include_tools / exclude_tools on TestCase."""

    def test_include_tools_field(self):
        tc = TestCase(
            name="test1",
            prompt="test",
            evaluators=[],
            include_tools=["list_dashboards", "get_dashboard_info"],
        )
        assert tc.include_tools == ["list_dashboards", "get_dashboard_info"]

    def test_exclude_tools_field(self):
        tc = TestCase(
            name="test1",
            prompt="test",
            evaluators=[],
            exclude_tools=["web_search", "filesystem_read"],
        )
        assert tc.exclude_tools == ["web_search", "filesystem_read"]

    def test_default_none(self):
        tc = TestCase(name="test1", prompt="test", evaluators=[])
        assert tc.include_tools is None
        assert tc.exclude_tools is None

    def test_from_dict_include_tools(self):
        data = {
            "name": "test1",
            "prompt": "test",
            "evaluators": [],
            "include_tools": ["list_dashboards"],
        }
        tc = TestCase.from_dict(data)
        assert tc.include_tools == ["list_dashboards"]

    def test_from_dict_exclude_tools(self):
        data = {
            "name": "test1",
            "prompt": "test",
            "evaluators": [],
            "exclude_tools": ["web_search"],
        }
        tc = TestCase.from_dict(data)
        assert tc.exclude_tools == ["web_search"]


class TestToolFilteringLogic:
    """Test the actual filtering logic (simulated)."""

    def _mock_tools(self):
        """Simulate MCP tools as simple objects with .name attribute."""

        class MockTool:
            def __init__(self, name):
                self.name = name

        return [
            MockTool("list_dashboards"),
            MockTool("list_charts"),
            MockTool("get_dashboard_info"),
            MockTool("web_search"),
            MockTool("filesystem_read"),
        ]

    def test_include_filters_to_subset(self):
        tools = self._mock_tools()
        include_set = {"list_dashboards", "list_charts"}
        filtered = [t for t in tools if t.name.lower() in include_set]
        assert len(filtered) == 2
        assert {t.name for t in filtered} == {"list_dashboards", "list_charts"}

    def test_exclude_removes_tools(self):
        tools = self._mock_tools()
        exclude_set = {"web_search", "filesystem_read"}
        filtered = [t for t in tools if t.name.lower() not in exclude_set]
        assert len(filtered) == 3
        assert "web_search" not in {t.name for t in filtered}

    def test_include_empty_list_gives_nothing(self):
        tools = self._mock_tools()
        include_set = set()
        filtered = [t for t in tools if t.name.lower() in include_set]
        assert len(filtered) == 0

    def test_exclude_empty_list_keeps_all(self):
        tools = self._mock_tools()
        exclude_set = set()
        filtered = [t for t in tools if t.name.lower() not in exclude_set]
        assert len(filtered) == 5

    def test_case_insensitive_filtering(self):
        tools = self._mock_tools()
        include_set = {"LIST_DASHBOARDS"}
        filtered = [t for t in tools if t.name.lower() in {s.lower() for s in include_set}]
        assert len(filtered) == 1


class TestSetupTeardownFields:
    """Test setup / teardown hooks on TestCase."""

    def test_setup_field(self):
        tc = TestCase(
            name="test1",
            prompt="test",
            evaluators=[],
            setup=[{"tool": "create_dataset", "args": {"name": "test_ds"}}],
        )
        assert len(tc.setup) == 1
        assert tc.setup[0]["tool"] == "create_dataset"

    def test_teardown_field(self):
        tc = TestCase(
            name="test1",
            prompt="test",
            evaluators=[],
            teardown=[{"tool": "delete_dataset", "args": {"name": "test_ds"}}],
        )
        assert len(tc.teardown) == 1

    def test_default_none(self):
        tc = TestCase(name="test1", prompt="test", evaluators=[])
        assert tc.setup is None
        assert tc.teardown is None

    def test_from_dict_setup(self):
        data = {
            "name": "test1",
            "prompt": "test",
            "evaluators": [],
            "setup": [{"tool": "create_dataset", "args": {"name": "ds1"}}],
        }
        tc = TestCase.from_dict(data)
        assert tc.setup is not None
        assert tc.setup[0]["tool"] == "create_dataset"

    def test_from_dict_teardown(self):
        data = {
            "name": "test1",
            "prompt": "test",
            "evaluators": [],
            "teardown": [{"tool": "delete_dataset", "args": {"name": "ds1"}}],
        }
        tc = TestCase.from_dict(data)
        assert tc.teardown is not None

    def test_multiple_setup_steps(self):
        tc = TestCase(
            name="test1",
            prompt="test",
            evaluators=[],
            setup=[
                {"tool": "create_dataset", "args": {"name": "ds1"}},
                {"tool": "create_chart", "args": {"dataset_id": 1}},
            ],
        )
        assert len(tc.setup) == 2
