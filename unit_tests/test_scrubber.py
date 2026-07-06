"""Tests for the credential scrubber (testmcpy/scrubber.py).

Pins the contract that no secret — registered, env-derived, or
credential-shaped — survives into persisted data. The env-derived case
reproduces the incident where an LLM ran `echo $DD_API_KEY` as a tool
call and the output was persisted verbatim into a .results JSON that
later surfaced in a public repo.
"""

import pytest

from testmcpy import scrubber
from testmcpy.scrubber import (
    REDACTED,
    register_secret,
    register_secrets_from_auth,
    scrub_obj,
    scrub_text,
)


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    """Isolate every test from registered/env-cached secrets."""
    scrubber.reset_cache()
    yield
    scrubber.reset_cache()


class TestKnownValueScrubbing:
    def test_registered_secret_removed_from_string(self):
        register_secret("supersecretvalue123")
        assert scrub_text("token is supersecretvalue123 ok") == f"token is {REDACTED} ok"

    def test_registered_secret_removed_from_nested_obj(self):
        register_secret("deadbeefcafe1234")
        obj = {
            "results": [
                {"content": "output: deadbeefcafe1234", "is_error": False},
                ["deadbeefcafe1234", 42, None],
            ]
        }
        scrubbed = scrub_obj(obj)
        assert scrubbed["results"][0]["content"] == f"output: {REDACTED}"
        assert scrubbed["results"][1][0] == REDACTED
        assert scrubbed["results"][1][1] == 42

    def test_short_values_not_registered(self):
        register_secret("abc")
        assert scrub_text("abc def") == "abc def"

    def test_register_secrets_from_auth(self):
        register_secrets_from_auth(
            {
                "type": "jwt",
                "api_url": "https://api.example.com/v1/auth/",
                "api_token": "6ddb868b-8587-4abb-9a5c-ae0000000000",
                "api_secret": "a259c6ece3506e98c6be7bd8e4d13fba00000000",
            }
        )
        # token and secret redacted; type/url keys don't match sensitive names
        assert REDACTED in scrub_text("got 6ddb868b-8587-4abb-9a5c-ae0000000000")
        assert REDACTED in scrub_text("got a259c6ece3506e98c6be7bd8e4d13fba00000000")
        assert scrub_text("type jwt") == "type jwt"

    def test_input_not_mutated(self):
        register_secret("mutationcheck1234")
        obj = {"content": "mutationcheck1234"}
        scrub_obj(obj)
        assert obj["content"] == "mutationcheck1234"

    def test_register_secrets_from_nested_custom_headers(self):
        """custom_headers auth nests secrets under a headers dict."""
        register_secrets_from_auth(
            {
                "type": "custom_headers",
                "headers": {
                    "Authorization": "Bearer nested-header-secret-000",
                    "X-API-Key": "nested-apikey-value-111",
                    "X-Trace-Id": "not-a-secret-trace-id",
                },
            }
        )
        assert scrub_text("saw Bearer nested-header-secret-000") == f"saw {REDACTED}"
        assert REDACTED in scrub_text("got nested-apikey-value-111")
        # non-sensitive header name is not registered
        assert scrub_text("trace not-a-secret-trace-id") == "trace not-a-secret-trace-id"

    def test_register_secrets_from_auth_list_nesting(self):
        register_secrets_from_auth({"servers": [{"api_token": "listnested-token-222"}]})
        assert REDACTED in scrub_text("x listnested-token-222 y")


class TestEnvDerivedScrubbing:
    def test_env_api_key_value_scrubbed(self, monkeypatch):
        """The Dec 2025 reproduction: env var value echoed into a tool result."""
        monkeypatch.setenv("MY_SERVICE_API_KEY", "d82692081b4f497ecdc9ab28c1951f72")
        scrubber.reset_cache()
        tool_result = {
            "tool_call_id": "toolu_01",
            "content": "d82692081b4f497ecdc9ab28c1951f72",
            "is_error": False,
        }
        assert scrub_obj(tool_result)["content"] == REDACTED

    def test_env_non_sensitive_name_ignored(self, monkeypatch):
        monkeypatch.setenv("MY_FAVOURITE_COLOUR", "ultramarine-blue-12345")
        scrubber.reset_cache()
        assert scrub_text("ultramarine-blue-12345") == "ultramarine-blue-12345"

    def test_env_keyword_substring_not_matched(self, monkeypatch):
        """KEY/TOKEN must be whole segments: MONKEY and TOKENIZER are not secrets."""
        monkeypatch.setenv("FAVOURITE_MONKEY", "bonobo-genus-pan-12345")
        monkeypatch.setenv("TOKENIZER_PATH", "/opt/models/tokenizer.json")
        scrubber.reset_cache()
        assert scrub_text("bonobo-genus-pan-12345") == "bonobo-genus-pan-12345"
        assert scrub_text("/opt/models/tokenizer.json") == "/opt/models/tokenizer.json"

    def test_env_delimited_keyword_variants_matched(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghvalue-abcdef-123456")
        monkeypatch.setenv("AWS_SECRETS", "awsvalue-abcdef-123456")
        scrubber.reset_cache()
        assert scrub_text("a ghvalue-abcdef-123456") == f"a {REDACTED}"
        assert scrub_text("b awsvalue-abcdef-123456") == f"b {REDACTED}"

    def test_env_short_value_ignored(self, monkeypatch):
        monkeypatch.setenv("SOME_KEY", "short")
        scrubber.reset_cache()
        assert scrub_text("a short word") == "a short word"


class TestPatternScrubbing:
    def test_anthropic_key(self):
        assert scrub_text("sk-ant-api03-aaaaaaaaaaaaaaaaaaaaaaaa") == REDACTED

    def test_github_pat(self):
        assert scrub_text("ghp_" + "a" * 36) == REDACTED

    def test_aws_access_key(self):
        assert scrub_text("AKIAIOSFODNN7EXAMPLE") == REDACTED

    def test_bearer_header(self):
        out = scrub_text("Authorization: Bearer abcdefghij0123456789xyz")
        assert out == f"Authorization: Bearer {REDACTED}"

    def test_dd_headers(self):
        out = scrub_text(
            "curl -H 'DD-API-KEY: d82692081b4f497ecdc9ab28c1951f72' "
            "-H 'DD-APPLICATION-KEY: d79a312905bbf9c1ab5f2b90b30aa36efb78371e'"
        )
        assert "d8269208" not in out
        assert "d79a3129" not in out
        assert out.count(REDACTED) == 2

    def test_private_key_block(self):
        pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nlines\n-----END RSA PRIVATE KEY-----"
        assert scrub_text(pem) == REDACTED

    def test_git_sha_survives(self):
        sha = "49c109608ef00680ab0c6532029fe6c680b45533"
        assert scrub_text(f"commit {sha}") == f"commit {sha}"

    def test_uuid_survives(self):
        u = "73e7d23c-371e-4555-afce-a36a994f292e"
        assert scrub_text(f"run {u}") == f"run {u}"


class TestFieldNameScrubbing:
    def test_sensitive_field_masked_first8(self):
        obj = {"jwt_secret": "a259c6ece3506e98c6be7bd8e4d13fba"}
        assert scrub_obj(obj)["jwt_secret"] == "a259c6ec..."

    def test_short_sensitive_field_fully_masked(self):
        assert scrub_obj({"password": "hunter2"})["password"] == "***"

    def test_auth_token_field_masked(self):
        obj = {"auth_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"}
        assert scrub_obj(obj)["auth_token"] == "eyJhbGci..."

    def test_token_usage_not_masked(self):
        obj = {"token_usage": {"prompt": 100}, "tokens_input": 5}
        scrubbed = scrub_obj(obj)
        assert scrubbed["token_usage"] == {"prompt": 100}
        assert scrubbed["tokens_input"] == 5

    def test_none_sensitive_field_passes(self):
        assert scrub_obj({"auth_token": None})["auth_token"] is None


class TestResultToDictScrubbing:
    def test_test_result_to_dict_scrubs(self):
        from testmcpy.src.test_runner import TestResult

        register_secret("verysecretjwt000111")
        result = TestResult(
            test_name="t",
            passed=True,
            score=1.0,
            duration=1.0,
            auth_token="verysecretjwt000111",
            tool_results=[{"content": "echoed verysecretjwt000111", "is_error": False}],
            logs=["[SDK] token=verysecretjwt000111"],
        )
        d = result.to_dict()
        assert d["auth_token"] == "verysecr..."
        assert d["tool_results"][0]["content"] == f"echoed {REDACTED}"
        assert d["logs"][0] == f"[SDK] token={REDACTED}"


class TestStorageScrubbing:
    def test_save_question_result_scrubs_db_row(self, tmp_path):
        from datetime import datetime, timezone

        from testmcpy.storage import TestStorage

        register_secret("dbsecretvalue9876")
        storage = TestStorage(db_path=tmp_path / "t.db")
        storage.save_suite(suite_id="s1", name="s1", questions=[{"id": "q1"}])
        storage.save_run(
            run_id="r1",
            test_id="s1",
            test_version=1,
            model="m",
            provider="p",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        storage.save_question_result(
            run_id="r1",
            question_id="q1",
            passed=True,
            score=1.0,
            answer="the key is dbsecretvalue9876",
            tool_results=[{"content": "dbsecretvalue9876", "is_error": False}],
        )
        row = storage.get_run("r1")["question_results"][0]
        assert row["answer"] == f"the key is {REDACTED}"
        assert row["tool_results"][0]["content"] == REDACTED
