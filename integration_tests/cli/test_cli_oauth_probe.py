"""CLI registration and standalone validation coverage."""

from pathlib import Path

from testmcpy_oauth_probe.cli import main
from typer.testing import CliRunner

from testmcpy.cli import app

runner = CliRunner()


def _write_manifest(path: Path) -> None:
    path.write_text(
        """schema: testmcpy.io/oauth-smoke/v1
targets:
  example:
    mcp_url: https://mcp.example.test/mcp
    oauth:
      flow: none
""",
        encoding="utf-8",
    )


def test_typer_auth_validate_is_additive(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    _write_manifest(manifest)
    result = runner.invoke(app, ["auth", "validate", "--config", str(manifest)])
    assert result.exit_code == 0
    assert "Valid" in result.stdout
    assert "1 target" in result.stdout


def test_standalone_headless_validate_and_schema(tmp_path: Path, capsys: object) -> None:
    manifest = tmp_path / "manifest.yaml"
    _write_manifest(manifest)
    assert main(["validate", "--config", str(manifest)]) == 0
    assert main(["schema"]) == 0
    assert main(["schema", "--kind", "report"]) == 0
    result = runner.invoke(app, ["auth", "schema", "--kind", "report"])
    assert result.exit_code == 0
    assert "oauth-smoke-report/v1" in result.stdout
