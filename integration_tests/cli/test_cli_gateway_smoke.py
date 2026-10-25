"""`testmcpy gateway-smoke` registration and exit-code plumbing."""

import json
from pathlib import Path

from typer.testing import CliRunner

from testmcpy.cli import app

runner = CliRunner()
EXAMPLE = Path(__file__).resolve().parents[2] / "examples/gateway-smoke/gateway-smoke.example.yaml"


def test_validate_example_config() -> None:
    result = runner.invoke(app, ["gateway-smoke", "validate", "--config", str(EXAMPLE)])
    assert result.exit_code == 0
    assert "placeholders" in result.stdout


def test_run_of_unedited_example_is_blocked_not_pass(tmp_path: Path) -> None:
    out, junit = tmp_path / "report.json", tmp_path / "report.xml"
    result = runner.invoke(
        app,
        [
            "gateway-smoke", "run", "--config", str(EXAMPLE), "--format", "json",
            "--output", str(out), "--junit", str(junit),
        ],
    )  # fmt: skip
    assert result.exit_code == 3
    report = json.loads(out.read_text())
    assert report["status"] == "BLOCKED"
    assert report["usage"]["calls"] == 0
    assert junit.exists()


def test_run_rejects_unknown_output_format() -> None:
    result = runner.invoke(
        app, ["gateway-smoke", "run", "--config", str(EXAMPLE), "--format", "xml"]
    )
    assert result.exit_code == 2
