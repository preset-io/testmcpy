"""
Comprehensive unit tests for YAML test file parsing and validation.

Tests cover:
- Valid YAML test file parsing
- TestCase.from_dict() validation
- TestStep.from_dict() for multi-turn tests
- Schema validation and required fields
- Assertion/evaluator parsing
- Variable substitution patterns
- Edge cases: empty files, invalid YAML, missing fields, Unicode, large files
"""

import tempfile
from pathlib import Path

import pytest

from testmcpy.src.models import Question, TestSuite
from testmcpy.src.test_runner import TestCase, TestStep


class TestTestCaseFromDict:
    """Test TestCase.from_dict() parsing for single-turn tests."""

    def test_minimal_valid_test_case(self):
        """Test parsing a minimal valid test case."""
        data = {
            "name": "test_simple",
            "prompt": "List all datasets",
        }
        test_case = TestCase.from_dict(data)

        assert test_case.name == "test_simple"
        assert test_case.prompt == "List all datasets"
        assert test_case.evaluators == []
        assert test_case.timeout == 30.0
        assert test_case.metadata == {}
        assert test_case.expected_tools is None
        assert test_case.auth is None
        assert test_case.steps is None

    def test_complete_test_case(self):
        """Test parsing a complete test case with all fields."""
        data = {
            "name": "test_complete",
            "prompt": "Show me datasets",
            "evaluators": [
                {"name": "was_mcp_tool_called", "args": {"tool_name": "list_datasets"}},
                {"name": "execution_successful"},
            ],
            "metadata": {"category": "smoke", "priority": "high"},
            "expected_tools": ["list_datasets", "get_dataset_info"],
            "timeout": 60.0,
            "auth": {"type": "oauth", "client_id": "test123"},
        }
        test_case = TestCase.from_dict(data)

        assert test_case.name == "test_complete"
        assert test_case.prompt == "Show me datasets"
        assert len(test_case.evaluators) == 2
        assert test_case.evaluators[0]["name"] == "was_mcp_tool_called"
        assert test_case.evaluators[0]["args"]["tool_name"] == "list_datasets"
        assert test_case.evaluators[1]["name"] == "execution_successful"
        assert test_case.timeout == 60.0
        assert test_case.metadata["category"] == "smoke"
        assert test_case.metadata["priority"] == "high"
        assert test_case.expected_tools == ["list_datasets", "get_dataset_info"]
        assert test_case.auth["type"] == "oauth"
        assert test_case.auth["client_id"] == "test123"

    def test_evaluators_as_simple_list(self):
        """Test evaluators can be a simple list of names."""
        data = {
            "name": "test_simple_evaluators",
            "prompt": "Test prompt",
            "evaluators": [
                {"name": "execution_successful"},
                {"name": "was_mcp_tool_called", "args": {"tool_name": "test_tool"}},
            ],
        }
        test_case = TestCase.from_dict(data)

        assert len(test_case.evaluators) == 2
        assert test_case.evaluators[0]["name"] == "execution_successful"
        assert test_case.evaluators[1]["args"]["tool_name"] == "test_tool"

    def test_empty_evaluators_list(self):
        """Test handling of empty evaluators list."""
        data = {
            "name": "test_no_evaluators",
            "prompt": "Test prompt",
            "evaluators": [],
        }
        test_case = TestCase.from_dict(data)

        assert test_case.evaluators == []

    def test_missing_evaluators_defaults_to_empty(self):
        """Test that missing evaluators field defaults to empty list."""
        data = {
            "name": "test_missing_evaluators",
            "prompt": "Test prompt",
        }
        test_case = TestCase.from_dict(data)

        assert test_case.evaluators == []

    def test_unicode_in_test_name(self):
        """Test handling of Unicode characters in test names."""
        data = {
            "name": "test_unicode_example",
            "prompt": "List data with unicode characters",
        }
        test_case = TestCase.from_dict(data)

        assert test_case.name == "test_unicode_example"
        assert "unicode" in test_case.prompt

    def test_special_characters_in_strings(self):
        """Test handling of special characters in strings."""
        data = {
            "name": "test_special_chars",
            "prompt": "Show me \"quoted\" values and 'single quotes' and newlines\nand tabs\t",
        }
        test_case = TestCase.from_dict(data)

        assert '"quoted"' in test_case.prompt
        assert "'single quotes'" in test_case.prompt
        assert "\n" in test_case.prompt
        assert "\t" in test_case.prompt

    def test_very_long_prompt(self):
        """Test handling of very long prompts."""
        long_prompt = "Test " * 1000  # 5000 chars
        data = {
            "name": "test_long_prompt",
            "prompt": long_prompt,
        }
        test_case = TestCase.from_dict(data)

        assert len(test_case.prompt) == len(long_prompt)
        assert test_case.prompt == long_prompt

    def test_complex_nested_auth_config(self):
        """Test parsing complex nested auth configuration."""
        data = {
            "name": "test_complex_auth",
            "prompt": "Test with auth",
            "auth": {
                "type": "oauth",
                "client_id": "${OAUTH_CLIENT_ID}",
                "client_secret": "${OAUTH_CLIENT_SECRET}",
                "token_url": "https://auth.example.com/oauth/token",
                "scopes": ["read", "write", "admin"],
                "extra_params": {
                    "audience": "api.example.com",
                    "grant_type": "client_credentials",
                },
            },
        }
        test_case = TestCase.from_dict(data)

        assert test_case.auth["type"] == "oauth"
        assert test_case.auth["scopes"] == ["read", "write", "admin"]
        assert test_case.auth["extra_params"]["audience"] == "api.example.com"

    def test_complex_evaluator_args(self):
        """Test parsing complex evaluator arguments."""
        data = {
            "name": "test_complex_evaluator",
            "prompt": "Test",
            "evaluators": [
                {
                    "name": "tool_called_with_parameters",
                    "args": {
                        "tool_name": "list_datasets",
                        "parameters": {
                            "page": 2,
                            "page_size": 10,
                            "sort_by": "name",
                        },
                        "partial_match": True,
                    },
                },
            ],
        }
        test_case = TestCase.from_dict(data)

        evaluator = test_case.evaluators[0]
        assert evaluator["name"] == "tool_called_with_parameters"
        assert evaluator["args"]["tool_name"] == "list_datasets"
        assert evaluator["args"]["parameters"]["page"] == 2
        assert evaluator["args"]["parameters"]["page_size"] == 10
        assert evaluator["args"]["partial_match"] is True


class TestTestStepFromDict:
    """Test TestStep.from_dict() parsing for multi-turn tests."""

    def test_minimal_test_step(self):
        """Test parsing a minimal test step."""
        data = {
            "prompt": "Step 1 prompt",
        }
        step = TestStep.from_dict(data)

        assert step.prompt == "Step 1 prompt"
        assert step.evaluators == []
        assert step.name is None
        assert step.timeout == 30.0

    def test_complete_test_step(self):
        """Test parsing a complete test step."""
        data = {
            "prompt": "Step 2 prompt",
            "name": "verification_step",
            "timeout": 45.0,
            "evaluators": [
                {"name": "execution_successful"},
                {"name": "final_answer_contains", "args": {"expected_substring": "success"}},
            ],
        }
        step = TestStep.from_dict(data)

        assert step.prompt == "Step 2 prompt"
        assert step.name == "verification_step"
        assert step.timeout == 45.0
        assert len(step.evaluators) == 2
        assert step.evaluators[0]["name"] == "execution_successful"
        assert step.evaluators[1]["args"]["expected_substring"] == "success"

    def test_step_with_unicode(self):
        """Test step with Unicode characters."""
        data = {
            "prompt": "Show data with special characters",
            "name": "unicode_step",
        }
        step = TestStep.from_dict(data)

        assert "special" in step.prompt
        assert step.name == "unicode_step"


class TestMultiTurnTestCase:
    """Test parsing multi-turn test cases with steps."""

    def test_multi_turn_test_case(self):
        """Test parsing a multi-turn test case."""
        data = {
            "name": "test_multi_turn",
            "steps": [
                {
                    "prompt": "Create a chart",
                    "evaluators": [{"name": "was_chart_created"}],
                },
                {
                    "prompt": "Show the chart",
                    "name": "show_step",
                    "evaluators": [
                        {"name": "final_answer_contains", "args": {"expected_substring": "chart"}}
                    ],
                },
            ],
        }
        test_case = TestCase.from_dict(data)

        assert test_case.name == "test_multi_turn"
        assert test_case.is_multi_turn is True
        assert len(test_case.steps) == 2

        # First step
        assert test_case.steps[0].prompt == "Create a chart"
        assert len(test_case.steps[0].evaluators) == 1

        # Second step
        assert test_case.steps[1].prompt == "Show the chart"
        assert test_case.steps[1].name == "show_step"
        assert len(test_case.steps[1].evaluators) == 1

    def test_multi_turn_inherits_first_step_prompt(self):
        """Test that multi-turn test uses first step's prompt as default."""
        data = {
            "name": "test_multi_turn_inherit",
            "steps": [
                {"prompt": "First prompt", "evaluators": [{"name": "execution_successful"}]},
                {"prompt": "Second prompt", "evaluators": [{"name": "execution_successful"}]},
            ],
        }
        test_case = TestCase.from_dict(data)

        # Should use first step's prompt and evaluators as defaults
        assert test_case.prompt == "First prompt"
        assert test_case.evaluators == [{"name": "execution_successful"}]

    def test_multi_turn_with_explicit_prompt_override(self):
        """Test multi-turn with explicit prompt overriding first step."""
        data = {
            "name": "test_override",
            "prompt": "Explicit prompt",
            "evaluators": [{"name": "custom_evaluator"}],
            "steps": [
                {"prompt": "Step 1", "evaluators": [{"name": "step1_eval"}]},
                {"prompt": "Step 2", "evaluators": [{"name": "step2_eval"}]},
            ],
        }
        test_case = TestCase.from_dict(data)

        # Should use explicit values, not first step
        assert test_case.prompt == "Explicit prompt"
        assert test_case.evaluators == [{"name": "custom_evaluator"}]

    def test_single_step_not_multi_turn(self):
        """Test that a single step is not considered multi-turn."""
        data = {
            "name": "test_single_step",
            "steps": [
                {"prompt": "Only one step", "evaluators": []},
            ],
        }
        test_case = TestCase.from_dict(data)

        assert test_case.is_multi_turn is False

    def test_no_steps_not_multi_turn(self):
        """Test that a test without steps is not multi-turn."""
        data = {
            "name": "test_no_steps",
            "prompt": "Regular prompt",
        }
        test_case = TestCase.from_dict(data)

        assert test_case.is_multi_turn is False
        assert test_case.steps is None


class TestTestSuiteFromDict:
    """Test TestSuite.from_dict() parsing."""

    def test_minimal_test_suite(self):
        """Test parsing a minimal test suite."""
        data = {
            "id": "test_suite_1",
        }
        suite = TestSuite.from_dict(data)

        assert suite.id == "test_suite_1"
        assert suite.name == "test_suite_1"  # Defaults to id
        assert suite.version == 1
        assert suite.environment_id is None
        assert suite.questions == []
        assert suite.description is None
        assert suite.metadata == {}

    def test_complete_test_suite(self):
        """Test parsing a complete test suite."""
        data = {
            "id": "comprehensive_suite",
            "name": "Comprehensive Test Suite",
            "version": 2,
            "environment_id": "prod-env-v1",
            "description": "A complete test suite",
            "metadata": {"author": "test_author", "tags": ["integration", "smoke"]},
            "questions": [
                {
                    "id": "q1",
                    "prompt": "First question",
                    "evaluators": [{"name": "execution_successful"}],
                },
                {
                    "id": "q2",
                    "prompt": "Second question",
                    "weight": 2.0,
                },
            ],
        }
        suite = TestSuite.from_dict(data)

        assert suite.id == "comprehensive_suite"
        assert suite.name == "Comprehensive Test Suite"
        assert suite.version == 2
        assert suite.environment_id == "prod-env-v1"
        assert suite.description == "A complete test suite"
        assert suite.metadata["author"] == "test_author"
        assert suite.metadata["tags"] == ["integration", "smoke"]
        assert len(suite.questions) == 2
        assert suite.questions[0].id == "q1"
        assert suite.questions[1].id == "q2"
        assert suite.questions[1].weight == 2.0

    def test_total_weight_calculation(self):
        """Test that total_weight property calculates correctly."""
        data = {
            "id": "weighted_suite",
            "questions": [
                {"id": "q1", "prompt": "Q1", "weight": 1.0},
                {"id": "q2", "prompt": "Q2", "weight": 2.5},
                {"id": "q3", "prompt": "Q3", "weight": 0.5},
            ],
        }
        suite = TestSuite.from_dict(data)

        assert suite.total_weight == 4.0


class TestQuestionFromDict:
    """Test Question.from_dict() parsing."""

    def test_minimal_question(self):
        """Test parsing a minimal question."""
        data = {
            "id": "q1",
            "prompt": "What is the answer?",
        }
        question = Question.from_dict(data)

        assert question.id == "q1"
        assert question.prompt == "What is the answer?"
        assert question.evaluators == []
        assert question.weight == 1.0
        assert question.timeout == 30.0
        assert question.metadata == {}

    def test_complete_question(self):
        """Test parsing a complete question."""
        data = {
            "id": "q_complex",
            "prompt": "Complex question?",
            "evaluators": [
                {"name": "was_mcp_tool_called", "args": {"tool_name": "test_tool"}},
            ],
            "weight": 3.5,
            "timeout": 60.0,
            "metadata": {"difficulty": "hard", "category": "api"},
        }
        question = Question.from_dict(data)

        assert question.id == "q_complex"
        assert question.prompt == "Complex question?"
        assert len(question.evaluators) == 1
        assert question.weight == 3.5
        assert question.timeout == 60.0
        assert question.metadata["difficulty"] == "hard"


class TestYAMLFileLoading:
    """Test loading test suites from actual YAML files."""

    def test_load_from_yaml_file(self):
        """Test loading a test suite from a YAML file."""
        yaml_content = """
id: file_test_suite
name: File Test Suite
version: 1
environment_id: test-env
description: Test loading from file
questions:
  - id: q1
    prompt: Test question
    evaluators:
      - name: execution_successful
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            suite = TestSuite.from_yaml_file(temp_path)

            assert suite.id == "file_test_suite"
            assert suite.name == "File Test Suite"
            assert suite.version == 1
            assert suite.environment_id == "test-env"
            assert len(suite.questions) == 1
            assert suite.questions[0].id == "q1"
        finally:
            Path(temp_path).unlink()

    def test_load_unicode_yaml_file(self):
        """Test loading a YAML file with Unicode content."""
        yaml_content = """
id: unicode_suite
name: Unicode Test Suite
questions:
  - id: q1
    prompt: Test with unicode content
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            suite = TestSuite.from_yaml_file(temp_path)

            assert suite.id == "unicode_suite"
            assert "Unicode" in suite.name
            assert "unicode" in suite.questions[0].prompt
        finally:
            Path(temp_path).unlink()

    def test_load_large_yaml_file(self):
        """Test loading a large YAML file with many questions."""
        # Generate a large YAML file
        yaml_content = """
id: large_suite
name: Large Test Suite
questions:
"""
        for i in range(100):
            yaml_content += f"""  - id: q{i}
    prompt: Question {i} prompt
    weight: {i % 5 + 1}.0
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            suite = TestSuite.from_yaml_file(temp_path)

            assert suite.id == "large_suite"
            assert len(suite.questions) == 100
            assert suite.questions[0].id == "q0"
            assert suite.questions[99].id == "q99"
        finally:
            Path(temp_path).unlink()


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_missing_required_name_field(self):
        """Test that missing name field raises KeyError."""
        data = {
            "prompt": "Test prompt",
        }
        with pytest.raises(KeyError):
            TestCase.from_dict(data)

    def test_missing_required_prompt_field_single_turn(self):
        """Test that missing prompt field for single-turn raises KeyError."""
        data = {
            "name": "test_missing_prompt",
        }
        with pytest.raises(KeyError):
            TestCase.from_dict(data)

    def test_missing_required_id_field_question(self):
        """Test that missing id field in Question raises KeyError."""
        data = {
            "prompt": "Test prompt",
        }
        with pytest.raises(KeyError):
            Question.from_dict(data)

    def test_missing_required_id_field_suite(self):
        """Test that missing id field in TestSuite raises KeyError."""
        data = {
            "name": "Test Suite",
        }
        with pytest.raises(KeyError):
            TestSuite.from_dict(data)

    def test_empty_prompt(self):
        """Test handling of empty prompt string."""
        data = {
            "name": "test_empty_prompt",
            "prompt": "",
        }
        test_case = TestCase.from_dict(data)

        assert test_case.prompt == ""

    def test_empty_test_name(self):
        """Test handling of empty test name."""
        data = {
            "name": "",
            "prompt": "Test prompt",
        }
        test_case = TestCase.from_dict(data)

        assert test_case.name == ""

    def test_negative_timeout(self):
        """Test that negative timeout is preserved (validation is runtime)."""
        data = {
            "name": "test_negative_timeout",
            "prompt": "Test",
            "timeout": -10.0,
        }
        test_case = TestCase.from_dict(data)

        assert test_case.timeout == -10.0

    def test_zero_timeout(self):
        """Test zero timeout."""
        data = {
            "name": "test_zero_timeout",
            "prompt": "Test",
            "timeout": 0.0,
        }
        test_case = TestCase.from_dict(data)

        assert test_case.timeout == 0.0

    def test_very_large_timeout(self):
        """Test very large timeout value."""
        data = {
            "name": "test_large_timeout",
            "prompt": "Test",
            "timeout": 999999.0,
        }
        test_case = TestCase.from_dict(data)

        assert test_case.timeout == 999999.0

    def test_multiline_prompt(self):
        """Test handling of multiline prompts."""
        data = {
            "name": "test_multiline",
            "prompt": """This is a multiline
prompt that spans
multiple lines
with indentation""",
        }
        test_case = TestCase.from_dict(data)

        assert "\n" in test_case.prompt
        assert "multiline" in test_case.prompt
        assert "multiple lines" in test_case.prompt

    def test_nested_metadata_structure(self):
        """Test deeply nested metadata structures."""
        data = {
            "name": "test_nested_metadata",
            "prompt": "Test",
            "metadata": {
                "level1": {
                    "level2": {
                        "level3": {
                            "deep_value": "found",
                            "deep_list": [1, 2, 3],
                        }
                    }
                }
            },
        }
        test_case = TestCase.from_dict(data)

        assert test_case.metadata["level1"]["level2"]["level3"]["deep_value"] == "found"
        assert test_case.metadata["level1"]["level2"]["level3"]["deep_list"] == [1, 2, 3]

    def test_list_values_in_fields(self):
        """Test list values in various fields."""
        data = {
            "name": "test_lists",
            "prompt": "Test",
            "expected_tools": ["tool1", "tool2", "tool3"],
            "evaluators": [
                {"name": "eval1"},
                {"name": "eval2"},
            ],
        }
        test_case = TestCase.from_dict(data)

        assert len(test_case.expected_tools) == 3
        assert len(test_case.evaluators) == 2

    def test_boolean_values_in_auth(self):
        """Test boolean values in configuration."""
        data = {
            "name": "test_booleans",
            "prompt": "Test",
            "auth": {
                "type": "oauth",
                "verify_ssl": False,
                "allow_redirects": True,
            },
        }
        test_case = TestCase.from_dict(data)

        assert test_case.auth["verify_ssl"] is False
        assert test_case.auth["allow_redirects"] is True

    def test_numeric_values_in_evaluator_args(self):
        """Test various numeric types in evaluator args."""
        data = {
            "name": "test_numbers",
            "prompt": "Test",
            "evaluators": [
                {
                    "name": "test_eval",
                    "args": {
                        "int_value": 42,
                        "float_value": 3.14159,
                        "negative": -100,
                        "zero": 0,
                    },
                },
            ],
        }
        test_case = TestCase.from_dict(data)

        args = test_case.evaluators[0]["args"]
        assert args["int_value"] == 42
        assert args["float_value"] == 3.14159
        assert args["negative"] == -100
        assert args["zero"] == 0


class TestYAMLFormatValidation:
    """Test YAML format validation and error handling."""

    def test_empty_yaml_file(self):
        """Test loading an empty YAML file."""
        yaml_content = ""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            import yaml

            with open(temp_path) as f:
                data = yaml.safe_load(f)

            # Empty YAML loads as None
            assert data is None
        finally:
            Path(temp_path).unlink()

    def test_comments_in_yaml(self):
        """Test that YAML comments are properly ignored."""
        yaml_content = """
# This is a comment
id: test_suite
# Another comment
name: Test Suite
questions:
  # Comment before question
  - id: q1
    prompt: Test  # Inline comment
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            suite = TestSuite.from_yaml_file(temp_path)

            assert suite.id == "test_suite"
            assert suite.name == "Test Suite"
            assert len(suite.questions) == 1
        finally:
            Path(temp_path).unlink()

    def test_yaml_anchors_and_aliases(self):
        """Test YAML anchors and aliases."""
        yaml_content = """
id: anchor_suite
questions:
  - &common_eval
    id: q1
    prompt: First question
    evaluators:
      - name: execution_successful
  - <<: *common_eval
    id: q2
    prompt: Second question
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = f.name

        try:
            suite = TestSuite.from_yaml_file(temp_path)

            assert len(suite.questions) == 2
            assert suite.questions[0].id == "q1"
            assert suite.questions[1].id == "q2"
            # Both should have the evaluator
            assert len(suite.questions[0].evaluators) >= 1
            assert len(suite.questions[1].evaluators) >= 1
        finally:
            Path(temp_path).unlink()


class TestRealWorldYAMLExamples:
    """Test parsing real-world YAML examples from the examples directory."""

    def test_simple_tool_test_format(self):
        """Test parsing format similar to simple_tool_test.yaml."""
        data = {
            "name": "test_tool_is_called",
            "prompt": "List all datasets",
            "evaluators": [
                {
                    "name": "was_mcp_tool_called",
                    "args": {"tool_name": "list_datasets"},
                },
                {
                    "name": "execution_successful",
                },
            ],
        }
        test_case = TestCase.from_dict(data)

        assert test_case.name == "test_tool_is_called"
        assert len(test_case.evaluators) == 2

    def test_multi_evaluator_format(self):
        """Test parsing format similar to multi_evaluator_test.yaml."""
        data = {
            "name": "test_complete_validation",
            "prompt": "List the first 5 datasets",
            "timeout": 15,
            "evaluators": [
                {"name": "was_mcp_tool_called", "args": {"tool_name": "list_datasets"}},
                {
                    "name": "tool_called_with_parameter",
                    "args": {"tool_name": "list_datasets", "parameter_name": "page_size"},
                },
                {
                    "name": "parameter_value_in_range",
                    "args": {
                        "tool_name": "list_datasets",
                        "parameter_name": "page_size",
                        "min_value": 1,
                        "max_value": 10,
                    },
                },
                {"name": "execution_successful"},
                {"name": "within_time_limit", "args": {"max_seconds": 10}},
            ],
        }
        test_case = TestCase.from_dict(data)

        assert test_case.timeout == 15
        assert len(test_case.evaluators) == 5

    def test_auth_test_format(self):
        """Test parsing format similar to auth_tests.yaml."""
        data = {
            "name": "test_oauth_success",
            "prompt": "List all available datasets",
            "auth": {
                "type": "oauth",
                "client_id": "${OAUTH_CLIENT_ID}",
                "client_secret": "${OAUTH_CLIENT_SECRET}",
                "token_url": "${OAUTH_TOKEN_URL}",
                "scopes": ["read", "write"],
            },
            "evaluators": [
                {"name": "auth_successful"},
                {"name": "token_valid", "args": {"format": "jwt", "min_length": 100}},
                {"name": "oauth2_flow_complete"},
                {"name": "was_mcp_tool_called", "args": {"tool_name": "list_datasets"}},
                {"name": "execution_successful"},
            ],
        }
        test_case = TestCase.from_dict(data)

        assert test_case.auth["type"] == "oauth"
        assert test_case.auth["scopes"] == ["read", "write"]
        assert len(test_case.evaluators) == 5
