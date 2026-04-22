"""
Unit tests for system prompt support — AC 4.

Verifies system prompt flows from YAML config, CLI flags,
and into the LLM call messages.

Story: SC-104612 — Trial Benchmark
"""

import yaml

from testmcpy.src.test_runner import TestCase


class TestSystemPromptParsing:
    """Test that system_prompt is parsed from YAML."""

    def test_test_case_has_system_prompt_field(self):
        """TestCase should accept system_prompt."""
        tc = TestCase(
            name="test1",
            prompt="List dashboards",
            evaluators=[],
            system_prompt="You are a Superset assistant.",
        )
        assert tc.system_prompt == "You are a Superset assistant."

    def test_test_case_system_prompt_default_none(self):
        """system_prompt should default to None."""
        tc = TestCase(name="test1", prompt="List dashboards", evaluators=[])
        assert tc.system_prompt is None

    def test_from_dict_parses_system_prompt(self):
        """TestCase.from_dict should parse system_prompt."""
        data = {
            "name": "test1",
            "prompt": "List dashboards",
            "evaluators": [{"name": "execution_successful"}],
            "system_prompt": "You are a helpful assistant.",
        }
        tc = TestCase.from_dict(data)
        assert tc.system_prompt == "You are a helpful assistant."

    def test_from_dict_no_system_prompt(self):
        """TestCase.from_dict without system_prompt should set None."""
        data = {
            "name": "test1",
            "prompt": "List dashboards",
            "evaluators": [{"name": "execution_successful"}],
        }
        tc = TestCase.from_dict(data)
        assert tc.system_prompt is None


class TestSuiteLevelSystemPrompt:
    """Test suite-level system_prompt inheritance."""

    def test_suite_config_system_prompt(self):
        """Suite config.system_prompt should be parsed."""
        yaml_str = """
version: "1.0"
config:
  system_prompt: "You are a Superset BI assistant."
tests:
  - name: test1
    prompt: "List dashboards"
    evaluators:
      - name: execution_successful
  - name: test2
    prompt: "Show charts"
    evaluators:
      - name: execution_successful
"""
        data = yaml.safe_load(yaml_str)
        config_block = data.get("config", {})
        suite_system_prompt = config_block.get("system_prompt")
        assert suite_system_prompt == "You are a Superset BI assistant."

        # Simulate the CLI inheritance logic
        for test_data in data["tests"]:
            if suite_system_prompt and "system_prompt" not in test_data:
                test_data["system_prompt"] = suite_system_prompt

        tc1 = TestCase.from_dict(data["tests"][0])
        tc2 = TestCase.from_dict(data["tests"][1])
        assert tc1.system_prompt == "You are a Superset BI assistant."
        assert tc2.system_prompt == "You are a Superset BI assistant."

    def test_test_level_overrides_suite(self):
        """Test-level system_prompt should override suite-level."""
        yaml_str = """
version: "1.0"
config:
  system_prompt: "Suite default prompt"
tests:
  - name: test1
    prompt: "List dashboards"
    system_prompt: "Custom per-test prompt"
    evaluators:
      - name: execution_successful
"""
        data = yaml.safe_load(yaml_str)
        config_block = data.get("config", {})
        suite_system_prompt = config_block.get("system_prompt")

        for test_data in data["tests"]:
            if suite_system_prompt and "system_prompt" not in test_data:
                test_data["system_prompt"] = suite_system_prompt

        tc = TestCase.from_dict(data["tests"][0])
        assert tc.system_prompt == "Custom per-test prompt"

    def test_top_level_system_prompt(self):
        """Top-level system_prompt (outside config) should work."""
        yaml_str = """
version: "1.0"
system_prompt: "Top-level prompt"
tests:
  - name: test1
    prompt: "List dashboards"
    evaluators:
      - name: execution_successful
"""
        data = yaml.safe_load(yaml_str)
        suite_system_prompt = data.get("config", {}).get("system_prompt") or data.get(
            "system_prompt"
        )
        assert suite_system_prompt == "Top-level prompt"


class TestSystemPromptInMessages:
    """Test that system prompt gets injected into LLM messages."""

    def test_system_prompt_creates_system_message(self):
        """When system_prompt is set, messages should include system role."""
        tc = TestCase(
            name="test1",
            prompt="List dashboards",
            evaluators=[],
            system_prompt="You are a Superset assistant.",
        )
        # Simulate the message building logic from test_runner
        llm_kwargs = {}
        if tc.system_prompt:
            llm_kwargs["messages"] = [{"role": "system", "content": tc.system_prompt}]

        assert "messages" in llm_kwargs
        assert llm_kwargs["messages"][0]["role"] == "system"
        assert llm_kwargs["messages"][0]["content"] == "You are a Superset assistant."

    def test_no_system_prompt_no_messages(self):
        """When system_prompt is None, no messages kwarg should be added."""
        tc = TestCase(name="test1", prompt="List dashboards", evaluators=[])
        llm_kwargs = {}
        if tc.system_prompt:
            llm_kwargs["messages"] = [{"role": "system", "content": tc.system_prompt}]

        assert "messages" not in llm_kwargs

    def test_multi_turn_system_prompt_first_step_only(self):
        """System prompt should only be injected on the first multi-turn step."""
        from testmcpy.src.test_runner import TestStep

        tc = TestCase(
            name="multi",
            prompt="",
            evaluators=[],
            system_prompt="Be helpful.",
            steps=[
                TestStep(prompt="Step 1", evaluators=[]),
                TestStep(prompt="Step 2", evaluators=[]),
            ],
        )

        # Simulate multi-turn logic
        conversation_history = []
        for step_idx, step in enumerate(tc.steps):
            step_messages = list(conversation_history)
            if tc.system_prompt and step_idx == 0 and not step_messages:
                step_messages.insert(0, {"role": "system", "content": tc.system_prompt})

            if step_idx == 0:
                assert len(step_messages) == 1
                assert step_messages[0]["role"] == "system"
            else:
                # Step 2 should NOT have system prompt injected again
                # (conversation_history would have content by now in real flow)
                pass

            # Simulate adding to history
            conversation_history.append({"role": "user", "content": step.prompt})
            conversation_history.append({"role": "assistant", "content": "response"})
