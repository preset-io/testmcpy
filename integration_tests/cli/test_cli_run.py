"""Integration tests for the run command."""

import yaml


def test_run_help(runner, cli_app):
    """run --help should display usage information."""
    result = runner.invoke(cli_app, ["run", "--help"])
    assert result.exit_code == 0
    assert "test" in result.stdout.lower()


def test_run_missing_test_path(runner, cli_app):
    """run without a test path argument should fail."""
    result = runner.invoke(cli_app, ["run"])
    assert result.exit_code != 0


def test_run_nonexistent_file(runner, cli_app, tmp_path):
    """run with a nonexistent file should fail."""
    fake_path = tmp_path / "does_not_exist.yaml"
    result = runner.invoke(cli_app, ["run", str(fake_path)])
    assert result.exit_code != 0


def test_run_dry_run_with_valid_file(runner, cli_app, tmp_path):
    """run --dry-run with a valid test file should succeed without calling LLM."""
    test_file = tmp_path / "test.yaml"
    test_data = {
        "version": "1.0",
        "tests": [
            {
                "name": "test_hello",
                "prompt": "Say hello",
                "evaluators": [
                    {
                        "name": "execution_successful",
                    }
                ],
            }
        ],
    }
    test_file.write_text(yaml.dump(test_data, default_flow_style=False))
    result = runner.invoke(cli_app, ["run", str(test_file), "--dry-run"])
    assert result.exit_code == 0


def _write_suite(tmp_path, suite_fields):
    """Write a minimal one-test suite YAML with the given top-level fields."""
    test_file = tmp_path / "suite.yaml"
    data = {
        "version": "1.0",
        **suite_fields,
        "tests": [
            {"name": "q1", "prompt": "hello", "evaluators": [{"name": "execution_successful"}]}
        ],
    }
    test_file.write_text(yaml.dump(data, default_flow_style=False))
    return test_file


def test_explicit_model_overrides_suite_default_sentinel(runner, cli_app, tmp_path):
    """An explicit --model must win over a suite-level `model: default` sentinel.

    Chatbot suites declare `model: default` ("let the provider pick"); previously
    `suite_model or model` let that swallow an explicit override so the chosen
    model never reached the provider or the saved run.
    """
    test_file = _write_suite(tmp_path, {"provider": "assistant", "model": "default"})
    result = runner.invoke(
        cli_app,
        [
            "run",
            str(test_file),
            "--provider",
            "assistant",
            "--model",
            "claude-opus-4-7",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "assistant / claude-opus-4-7" in result.stdout


def test_suite_default_sentinel_preserved_without_override(runner, cli_app, tmp_path):
    """Without an explicit --model, a suite `model: default` stays 'default'."""
    test_file = _write_suite(tmp_path, {"provider": "assistant", "model": "default"})
    result = runner.invoke(cli_app, ["run", str(test_file), "--provider", "assistant", "--dry-run"])
    assert result.exit_code == 0
    assert "assistant / default" in result.stdout


def test_real_suite_model_pin_preserved(runner, cli_app, tmp_path):
    """A real suite-level `model:` still pins the model when no --model is given."""
    test_file = _write_suite(tmp_path, {"model": "claude-haiku-4-5"})
    result = runner.invoke(cli_app, ["run", str(test_file), "--dry-run"])
    assert result.exit_code == 0
    assert "claude-haiku-4-5" in result.stdout


def test_run_dry_run_directory(runner, cli_app, tmp_path):
    """run --dry-run on a directory with test files should succeed."""
    test_file = tmp_path / "suite.yaml"
    test_data = {
        "version": "1.0",
        "tests": [
            {
                "name": "test_one",
                "prompt": "Do something",
                "evaluators": [{"name": "execution_successful"}],
            }
        ],
    }
    test_file.write_text(yaml.dump(test_data, default_flow_style=False))
    result = runner.invoke(cli_app, ["run", str(tmp_path), "--dry-run"])
    assert result.exit_code == 0


def test_run_verbose_flag(runner, cli_app):
    """run --verbose should be accepted as a valid flag."""
    result = runner.invoke(cli_app, ["run", "--help"])
    assert result.exit_code == 0
    assert "verbose" in result.stdout.lower()


def test_run_output_flag(runner, cli_app):
    """run --output should be accepted as a valid flag."""
    result = runner.invoke(cli_app, ["run", "--help"])
    assert result.exit_code == 0
    assert "output" in result.stdout.lower()


def test_run_report_flag(runner, cli_app):
    """run --report should be accepted as a valid flag."""
    result = runner.invoke(cli_app, ["run", "--help"])
    assert result.exit_code == 0
    assert "report" in result.stdout.lower()
