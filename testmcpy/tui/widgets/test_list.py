"""Test list widget for displaying test files in the TUI."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.table import Table
from rich.text import Text
from textual.widgets import Static
from textual.reactive import reactive
from textual.widget import Widget


@dataclass
class TestFileInfo:
    """Information about a test file."""

    name: str
    path: Path
    passed: Optional[int] = None
    total: Optional[int] = None
    status: str = "not_run"  # not_run, passed, failed
    last_run: Optional[datetime] = None
    cost: Optional[float] = None
    duration: Optional[float] = None


class TestList(Widget):
    """Widget to display a list of test files with their status."""

    # Reactive attributes for selected test index and filter
    selected_index = reactive(0)
    filter_status = reactive("all")  # all, passed, failed, not_run

    def __init__(self, tests_dir: Path = Path("tests"), **kwargs):
        """Initialize the test list."""
        super().__init__(**kwargs)
        self.tests_dir = tests_dir
        self.test_files: list[TestFileInfo] = []
        self.load_test_files()

    def load_test_files(self):
        """Load all test files from the tests directory."""
        self.test_files = []
        
        if not self.tests_dir.exists():
            return
        
        for file in sorted(self.tests_dir.glob("*.yaml")):
            test_info = TestFileInfo(
                name=file.stem,
                path=file,
                status="not_run"
            )
            self.test_files.append(test_info)

    def get_filtered_tests(self) -> list[TestFileInfo]:
        """Get filtered list of tests based on current filter."""
        if self.filter_status == "all":
            return self.test_files
        return [t for t in self.test_files if t.status == self.filter_status]

    def get_status_icon(self, status: str) -> tuple[str, str]:
        """Get icon and style for a test status.
        
        Returns:
            Tuple of (icon, style)
        """
        if status == "passed":
            return ("✓", "green")
        elif status == "failed":
            return ("✗", "red")
        else:
            return ("○", "dim")

    def watch_selected_index(self, value: int) -> None:
        """Called when selected_index changes."""
        self.refresh()

    def watch_filter_status(self, value: str) -> None:
        """Called when filter_status changes."""
        self.selected_index = 0
        self.refresh()

    def render(self) -> Table:
        """Render the test list as a Rich table."""
        table = Table(
            show_header=True,
            header_style="bold cyan",
            expand=True,
            box=None,
            padding=(0, 1),
        )
        
        table.add_column("Status", width=3, no_wrap=True)
        table.add_column("Test Name", style="bold", no_wrap=True)
        table.add_column("Results", width=10, justify="center")
        table.add_column("Last Run", width=15, style="dim")
        
        filtered_tests = self.get_filtered_tests()

        if not filtered_tests:
            # Show empty state
            table.add_row(Text("No tests found", style="dim italic"))
        
        for idx, test in enumerate(filtered_tests):
            icon, style = self.get_status_icon(test.status)
            
            # Build results column
            if test.passed is not None and test.total is not None:
                results = f"{test.passed}/{test.total}"
                if test.status == "passed":
                    results_style = "green"
                elif test.status == "failed":
                    results_style = "red"
                else:
                    results_style = "dim"
            else:
                results = "—"
                results_style = "dim"
            
            # Format last run time
            if test.last_run:
                now = datetime.now()
                diff = now - test.last_run
                
                if diff.total_seconds() < 60:
                    last_run = "just now"
                elif diff.total_seconds() < 3600:
                    mins = int(diff.total_seconds() / 60)
                    last_run = f"{mins} min{'s' if mins > 1 else ''} ago"
                elif diff.total_seconds() < 86400:
                    hours = int(diff.total_seconds() / 3600)
                    last_run = f"{hours} hour{'s' if hours > 1 else ''} ago"
                else:
                    days = int(diff.total_seconds() / 86400)
                    last_run = f"{days} day{'s' if days > 1 else ''} ago"
            else:
                last_run = "—"
            
            # Highlight selected row
            row_style = "reverse" if idx == self.selected_index else ""
            
            table.add_row(
                Text(icon, style=style),
                Text(test.name, style="bold" if idx == self.selected_index else ""),
                Text(results, style=results_style),
                Text(last_run),
                style=row_style,
            )
        
        return table

    def action_select_next(self):
        """Select the next test in the list."""
        filtered = self.get_filtered_tests()
        if filtered:
            self.selected_index = (self.selected_index + 1) % len(filtered)

    def action_select_previous(self):
        """Select the previous test in the list."""
        filtered = self.get_filtered_tests()
        if filtered:
            self.selected_index = (self.selected_index - 1) % len(filtered)

    def get_selected_test(self) -> Optional[TestFileInfo]:
        """Get the currently selected test."""
        filtered = self.get_filtered_tests()
        if 0 <= self.selected_index < len(filtered):
            return filtered[self.selected_index]
        return None

    def update_test_status(
        self,
        test_name: str,
        status: str,
        passed: Optional[int] = None,
        total: Optional[int] = None,
        cost: Optional[float] = None,
        duration: Optional[float] = None,
    ):
        """Update the status of a test."""
        for test in self.test_files:
            if test.name == test_name:
                test.status = status
                test.passed = passed
                test.total = total
                test.cost = cost
                test.duration = duration
                test.last_run = datetime.now()
                self.refresh()
                break
