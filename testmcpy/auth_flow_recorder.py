"""
Authentication flow recorder with export, replay, and comparison capabilities.

This module provides comprehensive recording of OAuth, JWT, and Bearer authentication
flows, allowing you to save, replay, and compare authentication sequences for debugging
and documentation purposes.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree


class AuthFlowStep:
    """Represents a single step in an authentication flow."""

    def __init__(
        self,
        step_name: str,
        step_type: Literal["request", "response", "validation", "extraction", "error"],
        data: dict[str, Any],
        success: bool = True,
        timestamp: float | None = None,
        duration: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ):
        """Initialize an authentication flow step.

        Args:
            step_name: Name/description of the step
            step_type: Type of step (request, response, validation, extraction, error)
            data: Data associated with the step
            success: Whether the step was successful
            timestamp: Timestamp of the step (defaults to current time)
            duration: Duration of the step in seconds
            metadata: Additional metadata for the step
        """
        self.step_name = step_name
        self.step_type = step_type
        self.data = data
        self.success = success
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.duration = duration
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert step to dictionary representation.

        Returns:
            Dictionary containing step data
        """
        return {
            "step_name": self.step_name,
            "step_type": self.step_type,
            "data": self.data,
            "success": self.success,
            "timestamp": self.timestamp,
            "duration": self.duration,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthFlowStep":
        """Create step from dictionary representation.

        Args:
            data: Dictionary containing step data

        Returns:
            AuthFlowStep instance
        """
        return cls(
            step_name=data["step_name"],
            step_type=data["step_type"],
            data=data["data"],
            success=data.get("success", True),
            timestamp=data.get("timestamp"),
            duration=data.get("duration", 0.0),
            metadata=data.get("metadata", {}),
        )


class AuthFlowRecording:
    """Represents a complete authentication flow recording."""

    def __init__(
        self,
        flow_name: str,
        auth_type: Literal["oauth", "jwt", "bearer"],
        protocol_version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Initialize an authentication flow recording.

        Args:
            flow_name: Name/description of the flow
            auth_type: Type of authentication (oauth, jwt, bearer)
            protocol_version: Version of the auth protocol (e.g., "OAuth 2.0")
            metadata: Additional metadata for the flow
        """
        self.flow_name = flow_name
        self.auth_type = auth_type
        self.protocol_version = protocol_version
        self.metadata = metadata or {}
        self.steps: list[AuthFlowStep] = []
        self.start_time = time.time()
        self.end_time: float | None = None
        self.success: bool | None = None
        self.error: str | None = None
        self.recording_id = f"{flow_name}_{int(self.start_time)}"

    def add_step(self, step: AuthFlowStep) -> None:
        """Add a step to the recording.

        Args:
            step: Step to add to the recording
        """
        self.steps.append(step)

    def finalize(self, success: bool, error: str | None = None) -> None:
        """Finalize the recording.

        Args:
            success: Whether the overall flow was successful
            error: Error message if flow failed
        """
        self.end_time = time.time()
        self.success = success
        self.error = error

    def get_duration(self) -> float:
        """Get total duration of the flow.

        Returns:
            Duration in seconds
        """
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    def get_step_count(self) -> int:
        """Get number of steps in the flow.

        Returns:
            Number of steps
        """
        return len(self.steps)

    def get_success_count(self) -> int:
        """Get number of successful steps.

        Returns:
            Number of successful steps
        """
        return sum(1 for step in self.steps if step.success)

    def get_failure_count(self) -> int:
        """Get number of failed steps.

        Returns:
            Number of failed steps
        """
        return sum(1 for step in self.steps if not step.success)

    def to_dict(self) -> dict[str, Any]:
        """Convert recording to dictionary representation.

        Returns:
            Dictionary containing recording data
        """
        return {
            "recording_id": self.recording_id,
            "flow_name": self.flow_name,
            "auth_type": self.auth_type,
            "protocol_version": self.protocol_version,
            "metadata": self.metadata,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.get_duration(),
            "success": self.success,
            "error": self.error,
            "step_count": self.get_step_count(),
            "success_count": self.get_success_count(),
            "failure_count": self.get_failure_count(),
            "steps": [step.to_dict() for step in self.steps],
            "created_at": datetime.fromtimestamp(self.start_time).isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthFlowRecording":
        """Create recording from dictionary representation.

        Args:
            data: Dictionary containing recording data

        Returns:
            AuthFlowRecording instance
        """
        recording = cls(
            flow_name=data["flow_name"],
            auth_type=data["auth_type"],
            protocol_version=data.get("protocol_version"),
            metadata=data.get("metadata", {}),
        )
        recording.recording_id = data["recording_id"]
        recording.start_time = data["start_time"]
        recording.end_time = data.get("end_time")
        recording.success = data.get("success")
        recording.error = data.get("error")

        for step_data in data.get("steps", []):
            recording.add_step(AuthFlowStep.from_dict(step_data))

        return recording


class AuthFlowRecorder:
    """Records complete OAuth/JWT/Bearer authentication flows."""

    def __init__(self, storage_dir: str | Path | None = None):
        """Initialize the auth flow recorder.

        Args:
            storage_dir: Directory to store recordings (defaults to ~/.testmcpy/auth_flows)
        """
        if storage_dir is None:
            storage_dir = Path.home() / ".testmcpy" / "auth_flows"
        self.storage_dir = Path(storage_dir)
        try:
            # Check if parent path exists as a file (not directory)
            testmcpy_dir = Path.home() / ".testmcpy"
            if testmcpy_dir.exists() and not testmcpy_dir.is_dir():
                # Remove the file and create directory instead
                testmcpy_dir.unlink()
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Fall back to temp directory if home directory fails
            import tempfile

            self.storage_dir = Path(tempfile.gettempdir()) / "testmcpy" / "auth_flows"
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.console = Console()
        self.current_recording: AuthFlowRecording | None = None

    def start_recording(
        self,
        flow_name: str,
        auth_type: Literal["oauth", "jwt", "bearer"],
        protocol_version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuthFlowRecording:
        """Start a new authentication flow recording.

        Args:
            flow_name: Name/description of the flow
            auth_type: Type of authentication (oauth, jwt, bearer)
            protocol_version: Version of the auth protocol
            metadata: Additional metadata for the flow

        Returns:
            The started recording
        """
        self.current_recording = AuthFlowRecording(
            flow_name=flow_name,
            auth_type=auth_type,
            protocol_version=protocol_version,
            metadata=metadata,
        )
        return self.current_recording

    def record_step(
        self,
        step_name: str,
        step_type: Literal["request", "response", "validation", "extraction", "error"],
        data: dict[str, Any],
        success: bool = True,
        duration: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a step in the current authentication flow.

        Args:
            step_name: Name/description of the step
            step_type: Type of step
            data: Data associated with the step
            success: Whether the step was successful
            duration: Duration of the step in seconds
            metadata: Additional metadata for the step

        Raises:
            RuntimeError: If no recording is currently active
        """
        if not self.current_recording:
            raise RuntimeError("No recording active. Call start_recording() first.")

        step = AuthFlowStep(
            step_name=step_name,
            step_type=step_type,
            data=data,
            success=success,
            duration=duration,
            metadata=metadata,
        )
        self.current_recording.add_step(step)

    def stop_recording(
        self, success: bool, error: str | None = None, auto_save: bool = True
    ) -> AuthFlowRecording:
        """Stop the current recording.

        Args:
            success: Whether the overall flow was successful
            error: Error message if flow failed
            auto_save: Whether to automatically save the recording

        Returns:
            The completed recording

        Raises:
            RuntimeError: If no recording is currently active
        """
        if not self.current_recording:
            raise RuntimeError("No recording active. Call start_recording() first.")

        self.current_recording.finalize(success=success, error=error)

        if auto_save:
            self.save_recording(self.current_recording)

        recording = self.current_recording
        self.current_recording = None
        return recording

    def save_recording(self, recording: AuthFlowRecording, filename: str | None = None) -> Path:
        """Save a recording to a JSON file.

        Args:
            recording: Recording to save
            filename: Optional custom filename (defaults to timestamped name)

        Returns:
            Path to the saved file
        """
        if filename is None:
            timestamp = datetime.fromtimestamp(recording.start_time).strftime("%Y%m%d_%H%M%S")
            filename = f"{recording.auth_type}_{recording.flow_name}_{timestamp}.json"

        # Sanitize filename
        filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
        if not filename.endswith(".json"):
            filename += ".json"

        filepath = self.storage_dir / filename
        filepath.write_text(json.dumps(recording.to_dict(), indent=2))
        return filepath

    def load_recording(self, filepath: str | Path) -> AuthFlowRecording:
        """Load a recording from a JSON file.

        Args:
            filepath: Path to the recording file

        Returns:
            Loaded recording

        Raises:
            FileNotFoundError: If file does not exist
            json.JSONDecodeError: If file is not valid JSON
        """
        filepath = Path(filepath)
        data = json.loads(filepath.read_text())
        return AuthFlowRecording.from_dict(data)

    def list_recordings(
        self,
        auth_type: Literal["oauth", "jwt", "bearer"] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """List available recordings.

        Args:
            auth_type: Filter by authentication type
            limit: Maximum number of recordings to return

        Returns:
            List of recording metadata dictionaries
        """
        recordings = []
        for filepath in sorted(self.storage_dir.glob("*.json"), reverse=True):
            try:
                data = json.loads(filepath.read_text())
                if auth_type is None or data.get("auth_type") == auth_type:
                    recordings.append(
                        {
                            "filepath": str(filepath),
                            "filename": filepath.name,
                            "recording_id": data.get("recording_id"),
                            "flow_name": data.get("flow_name"),
                            "auth_type": data.get("auth_type"),
                            "created_at": data.get("created_at"),
                            "duration": data.get("duration"),
                            "success": data.get("success"),
                            "step_count": data.get("step_count"),
                        }
                    )
                    if limit and len(recordings) >= limit:
                        break
            except (json.JSONDecodeError, KeyError):
                continue

        return recordings

    def delete_recording(self, filepath: str | Path) -> None:
        """Delete a recording file.

        Args:
            filepath: Path to the recording file

        Raises:
            FileNotFoundError: If file does not exist
        """
        Path(filepath).unlink()

    def compare_recordings(
        self, recording1: AuthFlowRecording, recording2: AuthFlowRecording
    ) -> dict[str, Any]:
        """Compare two recordings and generate a diff.

        Args:
            recording1: First recording
            recording2: Second recording

        Returns:
            Dictionary containing comparison results
        """
        comparison = {
            "recording1": {
                "id": recording1.recording_id,
                "name": recording1.flow_name,
                "success": recording1.success,
                "duration": recording1.get_duration(),
                "step_count": recording1.get_step_count(),
            },
            "recording2": {
                "id": recording2.recording_id,
                "name": recording2.flow_name,
                "success": recording2.success,
                "duration": recording2.get_duration(),
                "step_count": recording2.get_step_count(),
            },
            "differences": {
                "success_changed": recording1.success != recording2.success,
                "step_count_delta": recording2.get_step_count() - recording1.get_step_count(),
                "duration_delta": recording2.get_duration() - recording1.get_duration(),
                "step_differences": [],
            },
        }

        # Compare steps
        max_steps = max(len(recording1.steps), len(recording2.steps))
        for i in range(max_steps):
            step1 = recording1.steps[i] if i < len(recording1.steps) else None
            step2 = recording2.steps[i] if i < len(recording2.steps) else None

            if step1 and step2:
                if step1.step_name != step2.step_name:
                    comparison["differences"]["step_differences"].append(
                        {
                            "index": i,
                            "type": "name_changed",
                            "from": step1.step_name,
                            "to": step2.step_name,
                        }
                    )
                if step1.success != step2.success:
                    comparison["differences"]["step_differences"].append(
                        {
                            "index": i,
                            "type": "success_changed",
                            "step_name": step1.step_name,
                            "from": step1.success,
                            "to": step2.success,
                        }
                    )
            elif step1:
                comparison["differences"]["step_differences"].append(
                    {"index": i, "type": "removed", "step_name": step1.step_name}
                )
            elif step2:
                comparison["differences"]["step_differences"].append(
                    {"index": i, "type": "added", "step_name": step2.step_name}
                )

        return comparison

    def display_recording(self, recording: AuthFlowRecording) -> None:
        """Display a recording in the console.

        Args:
            recording: Recording to display
        """
        # Header
        success_icon = "✓" if recording.success else "✗"
        success_color = "green" if recording.success else "red"

        self.console.print(
            Panel(
                f"[bold]{recording.flow_name}[/bold]\n"
                f"Type: {recording.auth_type.upper()}\n"
                f"Protocol: {recording.protocol_version or 'N/A'}\n"
                f"Status: [{success_color}]{success_icon} {'Success' if recording.success else 'Failed'}[/{success_color}]\n"
                f"Duration: {recording.get_duration():.2f}s\n"
                f"Steps: {recording.get_step_count()} "
                f"({recording.get_success_count()} success, {recording.get_failure_count()} failed)",
                title="Auth Flow Recording",
                border_style="cyan",
            )
        )

        # Steps
        tree = Tree("[bold cyan]Authentication Steps[/bold cyan]")
        for i, step in enumerate(recording.steps, 1):
            icon = "✓" if step.success else "✗"
            color = "green" if step.success else "red"
            branch = tree.add(
                f"[{color}]{i}. {icon} {step.step_name}[/{color}] [dim]({step.duration:.2f}s)[/dim]"
            )

            # Add step details
            branch.add(f"Type: {step.step_type}")
            if step.metadata:
                branch.add(f"Metadata: {step.metadata}")

        self.console.print(tree)

        # Error if present
        if recording.error:
            self.console.print(
                Panel(
                    recording.error,
                    title="Error",
                    border_style="red",
                )
            )

    def display_comparison(self, comparison: dict[str, Any]) -> None:
        """Display a comparison between two recordings.

        Args:
            comparison: Comparison results from compare_recordings()
        """
        rec1 = comparison["recording1"]
        rec2 = comparison["recording2"]
        diffs = comparison["differences"]

        # Summary table
        table = Table(title="Recording Comparison", show_header=True)
        table.add_column("Metric")
        table.add_column("Recording 1")
        table.add_column("Recording 2")
        table.add_column("Delta")

        def format_delta(delta: float | int, positive_is_good: bool = False) -> str:
            if delta == 0:
                return "[dim]no change[/dim]"
            color = (
                "green"
                if (delta > 0 and positive_is_good) or (delta < 0 and not positive_is_good)
                else "red"
            )
            sign = "+" if delta > 0 else ""
            return f"[{color}]{sign}{delta}[/{color}]"

        table.add_row(
            "Name",
            rec1["name"],
            rec2["name"],
            "[dim]N/A[/dim]",
        )
        table.add_row(
            "Success",
            "✓" if rec1["success"] else "✗",
            "✓" if rec2["success"] else "✗",
            "Changed" if diffs["success_changed"] else "[dim]no change[/dim]",
        )
        table.add_row(
            "Duration",
            f"{rec1['duration']:.2f}s",
            f"{rec2['duration']:.2f}s",
            format_delta(diffs["duration_delta"]),
        )
        table.add_row(
            "Steps",
            str(rec1["step_count"]),
            str(rec2["step_count"]),
            format_delta(diffs["step_count_delta"]),
        )

        self.console.print(table)

        # Step differences
        if diffs["step_differences"]:
            self.console.print("\n[bold]Step Differences:[/bold]")
            for diff in diffs["step_differences"]:
                if diff["type"] == "name_changed":
                    self.console.print(
                        f"  Step {diff['index']}: Name changed from '{diff['from']}' to '{diff['to']}'"
                    )
                elif diff["type"] == "success_changed":
                    self.console.print(
                        f"  Step {diff['index']} ({diff['step_name']}): "
                        f"Success changed from {diff['from']} to {diff['to']}"
                    )
                elif diff["type"] == "removed":
                    self.console.print(
                        f"  [red]Step {diff['index']} removed: {diff['step_name']}[/red]"
                    )
                elif diff["type"] == "added":
                    self.console.print(
                        f"  [green]Step {diff['index']} added: {diff['step_name']}[/green]"
                    )
        else:
            self.console.print("\n[green]No step differences found[/green]")

    def export_to_json(self, recording: AuthFlowRecording, filepath: str | Path) -> Path:
        """Export a recording to a JSON file.

        Args:
            recording: Recording to export
            filepath: Path to the output file

        Returns:
            Path to the exported file
        """
        filepath = Path(filepath)
        filepath.write_text(json.dumps(recording.to_dict(), indent=2))
        return filepath

    def sanitize_recording(
        self, recording: AuthFlowRecording, keep_token_preview: bool = True
    ) -> AuthFlowRecording:
        """Create a sanitized copy of a recording with sensitive data removed.

        Args:
            recording: Recording to sanitize
            keep_token_preview: Whether to keep first 8 chars of tokens

        Returns:
            Sanitized copy of the recording
        """
        sanitized = AuthFlowRecording.from_dict(recording.to_dict())

        sensitive_keys = [
            "client_secret",
            "api_secret",
            "password",
            "token",
            "access_token",
            "refresh_token",
        ]

        def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
            sanitized_data = {}
            for key, value in data.items():
                key_lower = key.lower()
                if any(sensitive in key_lower for sensitive in sensitive_keys):
                    if isinstance(value, str):
                        if keep_token_preview and len(value) > 8:
                            sanitized_data[key] = value[:8] + "..."
                        else:
                            sanitized_data[key] = "***REDACTED***"
                    else:
                        sanitized_data[key] = value
                elif isinstance(value, dict):
                    sanitized_data[key] = sanitize_dict(value)
                else:
                    sanitized_data[key] = value
            return sanitized_data

        for step in sanitized.steps:
            step.data = sanitize_dict(step.data)

        return sanitized
