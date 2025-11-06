"""Test Manager Screen for the TUI."""

import asyncio
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from testmcpy.src.test_runner import TestCase, TestRunner
from testmcpy.tui.widgets.test_list import TestFileInfo, TestList


class TestDetailsPanel(Static):
    """Panel showing details of the selected test."""

    def __init__(self, **kwargs):
        """Initialize the test details panel."""
        super().__init__(**kwargs)
        self.test_info: Optional[TestFileInfo] = None
        self.test_data: Optional[dict[str, Any]] = None

    def update_test(self, test_info: Optional[TestFileInfo]):
        """Update the panel with new test information."""
        self.test_info = test_info
        
        # Load test file if available
        if test_info and test_info.path.exists():
            try:
                with open(test_info.path) as f:
                    self.test_data = yaml.safe_load(f)
            except Exception:
                self.test_data = None
        else:
            self.test_data = None
        
        self.refresh()

    def render(self) -> Panel:
        """Render the test details panel."""
        if not self.test_info:
            return Panel(
                Text("No test selected", style="dim italic"),
                title="Test Details",
                border_style="cyan",
            )

        # Build content
        lines = []
        
        # Test file name
        lines.append(Text(self.test_info.name, style="bold cyan"))
        lines.append("")
        
        # Test metadata
        metadata_table = Table(show_header=False, box=None, padding=(0, 2))
        metadata_table.add_column("Key", style="dim")
        metadata_table.add_column("Value")
        
        # Count tests in file
        if self.test_data and "tests" in self.test_data:
            test_count = len(self.test_data["tests"])
        else:
            test_count = 1
        
        metadata_table.add_row("Tests:", f"{test_count}")
        
        # Last run
        if self.test_info.last_run:
            metadata_table.add_row("Last run:", self.test_info.last_run.strftime("%Y-%m-%d %H:%M:%S"))
        else:
            metadata_table.add_row("Last run:", "Never")
        
        # Status
        if self.test_info.status == "passed":
            status_text = Text("✓ PASSED", style="bold green")
        elif self.test_info.status == "failed":
            status_text = Text("✗ FAILED", style="bold red")
        else:
            status_text = Text("○ NOT RUN", style="dim")
        metadata_table.add_row("Status:", status_text)
        
        # Cost and duration
        if self.test_info.cost is not None:
            metadata_table.add_row("Cost:", f"${self.test_info.cost:.4f}")
        
        if self.test_info.duration is not None:
            metadata_table.add_row("Duration:", f"{self.test_info.duration:.2f}s")
        
        lines.append(metadata_table)
        lines.append("")
        
        # Evaluators
        if self.test_data and "tests" in self.test_data:
            lines.append(Text("Evaluators:", style="bold"))
            
            # Get evaluators from first test (simplified)
            first_test = self.test_data["tests"][0]
            evaluators = first_test.get("evaluators", [])
            
            for evaluator in evaluators:
                if isinstance(evaluator, str):
                    lines.append(Text(f"  • {evaluator}", style="dim"))
                elif isinstance(evaluator, dict):
                    name = evaluator.get("name", "unknown")
                    lines.append(Text(f"  • {name}", style="dim"))
        
        # Combine all content
        content = "\n".join([str(line) if isinstance(line, Text) else str(line) for line in lines if isinstance(line, (str, Text))])
        
        # For tables, we need to render them separately
        from rich.console import Console, RenderableType
        from io import StringIO
        
        console_output = StringIO()
        console = Console(file=console_output, width=50)
        
        for line in lines:
            if isinstance(line, Table):
                console.print(line)
            elif isinstance(line, Text):
                console.print(line)
            elif isinstance(line, str):
                console.print(line)
        
        content = console_output.getvalue()
        
        return Panel(
            content,
            title=f"Test Details: {self.test_info.name}",
            border_style="cyan",
        )


class RecentActivityPanel(Static):
    """Panel showing recent test activity."""

    def __init__(self, **kwargs):
        """Initialize the recent activity panel."""
        super().__init__(**kwargs)
        self.recent_runs: list[dict[str, Any]] = []

    def add_activity(self, test_name: str, status: str, passed: int, total: int, cost: float):
        """Add a new activity entry."""
        self.recent_runs.insert(0, {
            "test_name": test_name,
            "status": status,
            "passed": passed,
            "total": total,
            "cost": cost,
            "timestamp": datetime.now(),
        })
        
        # Keep only last 5
        self.recent_runs = self.recent_runs[:5]
        self.refresh()

    def render(self) -> Panel:
        """Render the recent activity panel."""
        if not self.recent_runs:
            return Panel(
                Text("No recent activity", style="dim italic"),
                title="Recent Activity",
                border_style="dim",
            )

        lines = []
        for run in self.recent_runs:
            icon = "✓" if run["status"] == "passed" else "✗"
            style = "green" if run["status"] == "passed" else "red"
            
            # Calculate time ago
            now = datetime.now()
            diff = now - run["timestamp"]
            
            if diff.total_seconds() < 60:
                time_ago = "just now"
            elif diff.total_seconds() < 3600:
                mins = int(diff.total_seconds() / 60)
                time_ago = f"{mins}m ago"
            else:
                hours = int(diff.total_seconds() / 3600)
                time_ago = f"{hours}h ago"
            
            line = Text()
            line.append(icon + " ", style=style)
            line.append(time_ago, style="dim")
            line.append(f" {run['test_name']} ", style="")
            line.append(f"{run['passed']}/{run['total']} ", style=style)
            line.append(f"| ${run['cost']:.4f}", style="dim")
            
            lines.append(line)

        content = "\n".join(str(line) for line in lines)
        
        return Panel(
            content,
            title="Recent Activity",
            border_style="dim",
        )


class TestManagerScreen(Screen):
    """Test Manager Screen with test execution capabilities."""

    BINDINGS = [
        ("j", "select_next", "Next"),
        ("k", "select_previous", "Previous"),
        ("down", "select_next", "Next"),
        ("up", "select_previous", "Previous"),
        ("enter", "run_test", "Run"),
        ("r", "run_all", "Run All"),
        ("e", "edit_test", "Edit"),
        ("d", "delete_test", "Delete"),
        ("n", "new_test", "New"),
        ("f", "toggle_filter", "Filter"),
        ("h", "go_home", "Home"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, tests_dir: Path = Path("tests"), **kwargs):
        """Initialize the Test Manager Screen."""
        super().__init__(**kwargs)
        self.tests_dir = tests_dir
        self.test_list: Optional[TestList] = None
        self.test_details: Optional[TestDetailsPanel] = None
        self.recent_activity: Optional[RecentActivityPanel] = None

    def compose(self) -> ComposeResult:
        """Compose the Test Manager Screen layout."""
        yield Header()
        
        with Container(id="main-container"):
            with Horizontal(id="content-area"):
                # Left panel: Test list
                with Vertical(id="left-panel"):
                    yield Static("Test Files", id="left-title")
                    self.test_list = TestList(tests_dir=self.tests_dir, id="test-list")
                    yield self.test_list
                
                # Right panel: Test details
                with Vertical(id="right-panel"):
                    self.test_details = TestDetailsPanel(id="test-details")
                    yield self.test_details
            
            # Bottom panel: Recent activity
            self.recent_activity = RecentActivityPanel(id="recent-activity")
            yield self.recent_activity
        
        yield Footer()

    def on_mount(self) -> None:
        """Handle mount event."""
        # Update details panel with selected test
        if self.test_list:
            selected = self.test_list.get_selected_test()
            if self.test_details:
                self.test_details.update_test(selected)

    def action_select_next(self) -> None:
        """Select next test."""
        if self.test_list:
            self.test_list.action_select_next()
            selected = self.test_list.get_selected_test()
            if self.test_details:
                self.test_details.update_test(selected)

    def action_select_previous(self) -> None:
        """Select previous test."""
        if self.test_list:
            self.test_list.action_select_previous()
            selected = self.test_list.get_selected_test()
            if self.test_details:
                self.test_details.update_test(selected)

    def action_run_test(self) -> None:
        """Run the selected test."""
        if not self.test_list:
            return

        selected = self.test_list.get_selected_test()
        if not selected:
            return

        self.run_worker(self._run_test_file(selected), exclusive=True)

    def action_run_all(self) -> None:
        """Run all tests."""
        if not self.test_list:
            return

        for test in self.test_list.test_files:
            self.run_worker(self._run_test_file(test), exclusive=False)

    async def _run_test_file(self, test_info: TestFileInfo) -> None:
        """Run a specific test file."""
        try:
            # Load test file
            with open(test_info.path) as f:
                data = yaml.safe_load(f)
            
            # Create test runner
            from testmcpy.config import get_config
            config = get_config()
            
            runner = TestRunner(
                model=config.default_model or "claude-haiku-4-5",
                provider=config.default_provider or "anthropic",
                mcp_url=config.mcp_url,
                verbose=False,
            )
            
            # Parse test cases
            test_cases = []
            if "tests" in data:
                for test_data in data["tests"]:
                    test_cases.append(TestCase.from_dict(test_data))
            else:
                test_cases.append(TestCase.from_dict(data))
            
            # Run tests
            results = await runner.run_tests(test_cases)
            
            # Calculate summary
            total_passed = sum(1 for r in results if r.passed)
            total_tests = len(results)
            total_cost = sum(r.cost for r in results)
            total_duration = sum(r.duration for r in results)
            
            status = "passed" if total_passed == total_tests else "failed"
            
            # Update test status
            if self.test_list:
                self.test_list.update_test_status(
                    test_info.name,
                    status,
                    passed=total_passed,
                    total=total_tests,
                    cost=total_cost,
                    duration=total_duration,
                )
            
            # Add to recent activity
            if self.recent_activity:
                self.recent_activity.add_activity(
                    test_info.name,
                    status,
                    total_passed,
                    total_tests,
                    total_cost,
                )
            
            # Refresh details panel
            if self.test_details:
                selected = self.test_list.get_selected_test()
                self.test_details.update_test(selected)
            
        except Exception as e:
            # Handle error - could show in a modal or status bar
            print(f"Error running test: {e}")

    def action_edit_test(self) -> None:
        """Edit the selected test in $EDITOR."""
        if not self.test_list:
            return
        
        selected = self.test_list.get_selected_test()
        if not selected:
            return
        
        editor = os.environ.get("EDITOR", "nano")
        
        try:
            # Suspend the app and open editor
            with self.app.suspend():
                subprocess.run([editor, str(selected.path)])
            
            # Reload test files
            self.test_list.load_test_files()
            
            # Update details
            if self.test_details:
                selected = self.test_list.get_selected_test()
                self.test_details.update_test(selected)
        except Exception as e:
            print(f"Error editing test: {e}")

    def action_delete_test(self) -> None:
        """Delete the selected test (with confirmation)."""
        # TODO: Implement confirmation modal
        pass

    def action_new_test(self) -> None:
        """Create a new test file."""
        # TODO: Implement test creation wizard
        pass

    def action_toggle_filter(self) -> None:
        """Toggle test filter."""
        if not self.test_list:
            return
        
        filters = ["all", "passed", "failed", "not_run"]
        current_idx = filters.index(self.test_list.filter_status)
        next_idx = (current_idx + 1) % len(filters)
        self.test_list.filter_status = filters[next_idx]
        self.test_list.refresh()

    def action_go_home(self) -> None:
        """Go back to home screen."""
        # TODO: Implement navigation to home screen
        pass

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()
