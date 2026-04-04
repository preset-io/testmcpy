"""Integration tests for the coverage command."""

import yaml


def test_coverage_help(runner, cli_app):
    """coverage --help should display usage information."""
    result = runner.invoke(cli_app, ["coverage", "--help"])
    assert result.exit_code == 0
    assert "coverage" in result.stdout.lower()


def test_coverage_help_shows_format_option(runner, cli_app):
    """coverage --help should list the --format option."""
    result = runner.invoke(cli_app, ["coverage", "--help"])
    assert result.exit_code == 0
    assert "format" in result.stdout.lower()


def test_coverage_help_shows_output_option(runner, cli_app):
    """coverage --help should list the --output option."""
    result = runner.invoke(cli_app, ["coverage", "--help"])
    assert result.exit_code == 0
    assert "output" in result.stdout.lower()


def test_coverage_missing_arg(runner, cli_app):
    """coverage without a test directory should fail."""
    result = runner.invoke(cli_app, ["coverage"])
    assert result.exit_code != 0


def test_coverage_nonexistent_dir(runner, cli_app, tmp_path):
    """coverage with a nonexistent directory should fail."""
    fake_dir = tmp_path / "nonexistent"
    result = runner.invoke(cli_app, ["coverage", str(fake_dir)])
    assert result.exit_code != 0


def test_coverage_with_test_dir(runner, cli_app, tmp_path):
    """coverage on a directory with test files should succeed."""
    test_file = tmp_path / "test.yaml"
    test_data = {
        "version": "1.0",
        "tests": [
            {
                "name": "t1",
                "prompt": "hello",
                "evaluators": [
                    {
                        "name": "was_mcp_tool_called",
                        "args": {"tool_name": "health_check"},
                    }
                ],
            }
        ],
    }
    test_file.write_text(yaml.dump(test_data, default_flow_style=False))
    result = runner.invoke(cli_app, ["coverage", str(tmp_path)])
    assert result.exit_code == 0


def test_coverage_empty_dir(runner, cli_app, tmp_path):
    """coverage on an empty directory should succeed (0 files scanned)."""
    result = runner.invoke(cli_app, ["coverage", str(tmp_path)])
    assert result.exit_code == 0
    assert "0" in result.stdout


def test_coverage_json_format(runner, cli_app, tmp_path):
    """coverage --format json should produce JSON output."""
    test_file = tmp_path / "test.yaml"
    test_data = {
        "version": "1.0",
        "tests": [
            {
                "name": "t1",
                "prompt": "hello",
                "evaluators": [
                    {
                        "name": "was_mcp_tool_called",
                        "args": {"tool_name": "health_check"},
                    }
                ],
            }
        ],
    }
    test_file.write_text(yaml.dump(test_data, default_flow_style=False))
    result = runner.invoke(cli_app, ["coverage", str(tmp_path), "--format", "json"])
    assert result.exit_code == 0
