"""Fixture tests for the gateway smoke lane against a local fake MCP gateway.

Every scenario talks real HTTP to a loopback server (examples/gateway-smoke/
fake_gateway.py) through the probe's destination-safe transport, so transport
limits, framing and redaction are exercised end to end. Nothing here touches a
network beyond loopback, and nothing calls an LLM.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from testmcpy.gateway_smoke import ConfigError, Status, loads_config, run_smoke
from testmcpy.gateway_smoke import cli as smoke_cli
from testmcpy.gateway_smoke.models import EXIT_CODES, worst
from testmcpy.gateway_smoke.reporters import to_human, to_json, to_junit
from testmcpy.gateway_smoke.runner import _strip_url_queries, evaluate_assertion

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = REPO_ROOT / "examples/gateway-smoke/gateway-smoke.example.yaml"

_spec = importlib.util.spec_from_file_location(
    "fake_gateway", REPO_ROOT / "examples/gateway-smoke/fake_gateway.py"
)
assert _spec and _spec.loader
fake = importlib.util.module_from_spec(_spec)
sys.modules["fake_gateway"] = fake
_spec.loader.exec_module(fake)

CLIENT_SECRET = "fake-client-secret-0123456789"
ENV = {"SMOKE_CLIENT_SECRET": CLIENT_SECRET, "SMOKE_ACCESS_TOKEN": fake.ACCESS_TOKEN}
SECRETS = (CLIENT_SECRET, fake.ACCESS_TOKEN, "fake-session-0123456789")


def doc(url: str, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema": "testmcpy.io/gateway-smoke/v1",
        "environment": "local-fake",
        "mcp_url": f"{url}/mcp",
        "workspace": {"id": fake.CANARY_WORKSPACE_ID, "name": fake.CANARY_WORKSPACE_NAME},
        "allow_http_loopback": True,
        "auth": {
            "mode": "client_credentials",
            "client_id": fake.CLIENT_ID,
            "client_secret": {"env": "SMOKE_CLIENT_SECRET"},
        },
        "discovery": {
            "required_tools": [
                {
                    "name": "list_workspace_services",
                    "properties": ["workspace_id"],
                    "required": ["workspace_id"],
                },
                "call_tool",
            ]
        },
        "fixture": {
            "read_only": True,
            "tool": "list_workspace_services",
            "arguments": {"workspace_id": fake.CANARY_WORKSPACE_ID},
            "workspace_argument": "workspace_id",
            "expect": [
                {"path": "workspace_id", "equals": fake.CANARY_WORKSPACE_ID},
                {"path": "workspace_name", "equals": fake.CANARY_WORKSPACE_NAME},
                {"path": "services", "contains": "datasets"},
            ],
        },
    }
    for key, value in overrides.items():
        if value is None:
            base.pop(key, None)
        elif isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


@contextmanager
def gateway(**behavior: Any) -> Iterator[tuple[str, Any]]:
    with fake.serve(fake.Behavior(**behavior)) as served:
        yield served


async def smoke(url: str, env: dict[str, str] | None = None, **overrides: Any):
    config = loads_config(json.dumps(doc(url, **overrides)))
    return await run_smoke(config, environ=ENV if env is None else env)


def check(report: Any, check_id: str) -> Any:
    for step in report.steps:
        for item in step.checks:
            if item.id == check_id:
                return item
    raise AssertionError(
        f"no check {check_id!r}; have {[c.id for s in report.steps for c in s.checks]}"
    )


def step_status(report: Any) -> dict[str, str]:
    return {step.id: step.status.value for step in report.steps}


def assert_no_secret(text: str) -> None:
    for secret in SECRETS:
        assert secret not in text


# ---------------------------------------------------------------- PASS path


@pytest.mark.asyncio
async def test_pass_path_identity_one_read_and_bounded_calls() -> None:
    with gateway() as (url, behavior):
        report = await smoke(url)
    assert report.status is Status.PASS and report.exit_code == 0
    assert step_status(report) == {
        "protocol_auth": "PASS",
        "tool_discovery": "PASS",
        "fixture_read": "PASS",
    }
    payload = report.to_dict()
    assert payload["environment"] == "local-fake"
    assert payload["workspace"] == {
        "id": fake.CANARY_WORKSPACE_ID,
        "name": fake.CANARY_WORKSPACE_NAME,
    }
    assert payload["lane"] == {"llm_calls": 0, "writes": 0, "read_only": True}
    # Exactly the one approved fixture call, bound to the configured workspace.
    assert behavior.tool_calls == [
        {
            "name": "list_workspace_services",
            "arguments": {"workspace_id": fake.CANARY_WORKSPACE_ID},
        }
    ]
    assert payload["usage"]["calls"] == len(payload["calls"]) <= payload["limits"]["max_calls"]
    # The lane never enumerates workspaces and never leaves the configured host.
    assert not any(c["name"] == "list_workspaces" for c in behavior.tool_calls)
    assert {c["url"].split("/")[2] for c in payload["calls"]} == {url.split("//")[1]}


@pytest.mark.asyncio
async def test_bearer_mode_pass() -> None:
    with gateway() as (url, behavior):
        config_doc = doc(url)
        config_doc["auth"] = {"mode": "bearer", "access_token": {"env": "SMOKE_ACCESS_TOKEN"}}
        report = await run_smoke(loads_config(json.dumps(config_doc)), environ=ENV)
        assert report.status is Status.PASS
        assert not any(r["path"] == "/token" for r in behavior.requests)
    assert_no_secret(to_json(report) + to_junit(report) + to_human(report))


# ---------------------------------------------------------------- FAIL paths


@pytest.mark.parametrize(
    ("behavior", "failing_check"),
    [
        ({"unauth_status": 200}, "mcp.auth.unauthorized.status"),
        ({"send_challenge": False}, "mcp.auth.challenge.bearer"),
        ({"prm_resource": "http://127.0.0.1:1/other"}, "rfc9728.resource.identity"),
        ({"protocol_version": "2024-11-05"}, "mcp.initialize.contract"),
        ({"capabilities": {"prompts": {}}}, "mcp.initialize.capabilities"),
        ({"initialize_status": 503}, "mcp.initialize.http_status"),
    ],
)
@pytest.mark.asyncio
async def test_protocol_and_auth_failures(behavior: dict[str, Any], failing_check: str) -> None:
    with gateway(**behavior) as (url, served):
        report = await smoke(url)
    assert report.status is Status.FAIL and report.exit_code == 1
    assert check(report, failing_check).status is Status.FAIL
    assert report.steps[0].status is Status.FAIL
    if failing_check.startswith(
        ("mcp.initialize.contract", "mcp.initialize.http", "mcp.initialize.cap")
    ):
        # No session, so nothing after step 1 may have run.
        assert served.tool_calls == []
        assert step_status(report)["fixture_read"] == "SKIPPED"


@pytest.mark.asyncio
async def test_required_tool_missing_fails_and_fixture_is_not_called() -> None:
    with gateway(drop_tools=("list_workspace_services",)) as (url, behavior):
        report = await smoke(url)
    assert report.status is Status.FAIL
    assert check(report, "tools_list.required.list_workspace_services").status is Status.FAIL
    assert check(report, "fixture.tool.advertised").status is Status.FAIL
    assert behavior.tool_calls == []


@pytest.mark.asyncio
async def test_required_tool_shape_mismatch_fails() -> None:
    with gateway() as (url, _):
        report = await smoke(
            url,
            discovery={
                "required_tools": [
                    {"name": "list_workspace_services", "properties": ["no_such_property"]}
                ]
            },
        )
    item = check(report, "tools_list.required.list_workspace_services")
    assert item.status is Status.FAIL
    assert item.evidence["missing_properties"] == ["no_such_property"]


@pytest.mark.asyncio
async def test_tool_count_budget_fails() -> None:
    with gateway() as (url, _):
        report = await smoke(url, discovery={"max_tools": 2})
    assert check(report, "tools_list.budget.tool_count").status is Status.FAIL
    assert report.status is Status.FAIL


@pytest.mark.asyncio
async def test_tools_bytes_budget_fails() -> None:
    with gateway(pad_description=4000) as (url, _):
        report = await smoke(url, discovery={"max_bytes": 4096})
    assert check(report, "tools_list.budget.bytes").status is Status.FAIL


@pytest.mark.asyncio
async def test_page_cap_fails_when_catalogue_is_not_exhausted() -> None:
    with gateway(endless_cursor=True) as (url, behavior):
        report = await smoke(url, discovery={"max_pages": 2})
        lists = [r for r in behavior.requests if r["path"] == "/mcp"]
    assert check(report, "tools_list.catalogue").status is Status.FAIL
    assert check(report, "tools_list.catalogue").evidence["pages"] == 2
    # initialize + 2 pages + ack + unauthenticated challenge: never a third page.
    assert len(lists) <= 5


@pytest.mark.parametrize(
    ("behavior", "failing_check"),
    [
        ({"call_mode": "wrong_value"}, "fixture.expect.1"),
        ({"call_mode": "is_error"}, "fixture.call.result"),
        ({"call_mode": "rpc_error"}, "fixture.call.result"),
        ({"call_mode": "status_500"}, "fixture.call.http_status"),
    ],
)
@pytest.mark.asyncio
async def test_fixture_failures(behavior: dict[str, Any], failing_check: str) -> None:
    with gateway(**behavior) as (url, served):
        report = await smoke(url)
    assert report.status is Status.FAIL
    assert check(report, failing_check).status is Status.FAIL
    assert len(served.tool_calls) == 1


# ---------------------------------------------------------------- BLOCKED


@pytest.mark.asyncio
async def test_missing_credentials_is_blocked_with_no_network() -> None:
    with gateway() as (url, behavior):
        report = await smoke(url, env={})
        assert behavior.requests == []
    assert report.status is Status.BLOCKED and report.exit_code == 3
    item = check(report, "preflight.credentials")
    assert item.status is Status.BLOCKED
    assert item.evidence["missing_env"] == ["SMOKE_CLIENT_SECRET"]
    assert step_status(report)["tool_discovery"] == "SKIPPED"
    assert report.to_dict()["usage"]["calls"] == 0


@pytest.mark.asyncio
async def test_missing_fixture_is_blocked_with_no_network() -> None:
    with gateway() as (url, behavior):
        report = await smoke(url, fixture=None)
        assert behavior.requests == []
    assert report.status is Status.BLOCKED
    assert check(report, "preflight.fixture").status is Status.BLOCKED


@pytest.mark.asyncio
async def test_placeholder_config_is_blocked_and_never_contacts_the_target() -> None:
    config = loads_config(EXAMPLE.read_text(encoding="utf-8"))
    report = await run_smoke(config, environ=ENV)
    assert report.status is Status.BLOCKED
    assert check(report, "preflight.placeholders").status is Status.BLOCKED
    assert report.to_dict()["usage"]["calls"] == 0


@pytest.mark.parametrize("mode", ["invalid_client", "server_error"])
@pytest.mark.asyncio
async def test_unavailable_machine_oauth_is_blocked_never_pass(mode: str) -> None:
    with gateway(token_mode=mode) as (url, behavior):
        report = await smoke(url)
    assert report.status is Status.BLOCKED and report.exit_code == 3
    token = check(report, "oauth.token.acquire")
    assert token.status is Status.BLOCKED
    assert "credential unavailable" in token.message
    assert behavior.tool_calls == []
    assert step_status(report)["fixture_read"] == "SKIPPED"


@pytest.mark.asyncio
async def test_unreachable_token_endpoint_is_blocked() -> None:
    with gateway() as (url, _):
        report = await smoke(url, auth={"token_endpoint": "http://127.0.0.1:1/token"})
    assert report.status is Status.BLOCKED


@pytest.mark.asyncio
async def test_fixture_tool_advertising_destructive_hint_is_refused() -> None:
    risky = {
        "name": "fetch_report",
        "description": "looks harmless",
        "inputSchema": {"type": "object"},
        "annotations": {"destructiveHint": True},
    }
    with gateway(extra_tools=[risky]) as (url, behavior):
        report = await smoke(
            url,
            fixture={
                "tool": "fetch_report",
                "arguments": {"workspace_id": fake.CANARY_WORKSPACE_ID},
            },
        )
    assert report.status is Status.BLOCKED
    assert check(report, "fixture.read_only.guard").status is Status.BLOCKED
    assert behavior.tool_calls == []


# ---------------------------------------------------------------- ERROR


@pytest.mark.parametrize(
    ("behavior", "erroring_check"),
    [
        ({"initialize_body": "{not json"}, "mcp.initialize.protocol"),
        ({"call_mode": "malformed"}, "fixture.call.protocol"),
        ({"token_mode": "malformed"}, "oauth.token.acquire"),
    ],
)
@pytest.mark.asyncio
async def test_malformed_responses_are_error(behavior: dict[str, Any], erroring_check: str) -> None:
    with gateway(**behavior) as (url, _):
        report = await smoke(url)
    assert report.status is Status.ERROR and report.exit_code == 2
    assert check(report, erroring_check).status is Status.ERROR


@pytest.mark.asyncio
async def test_unreachable_gateway_is_error() -> None:
    config_doc = doc("http://127.0.0.1:1")
    report = await run_smoke(loads_config(json.dumps(config_doc)), environ=ENV)
    assert report.status is Status.ERROR


# ---------------------------------------------------------------- limits


@pytest.mark.asyncio
async def test_max_calls_is_enforced_before_the_request_is_sent() -> None:
    with gateway() as (url, behavior):
        report = await smoke(url, limits={"max_calls": 4})
        # The server never sees more requests than the cap.
        assert len(behavior.requests) <= 4
    assert report.status is Status.ERROR
    assert report.to_dict()["usage"]["calls"] <= 4
    assert any("max_calls" in c.message for s in report.steps for c in s.checks)


@pytest.mark.asyncio
async def test_per_call_timeout_is_enforced() -> None:
    with gateway(call_delay=1.0) as (url, _):
        report = await smoke(
            url, limits={"per_call_timeout_seconds": 0.3, "total_timeout_seconds": 20}
        )
    assert report.status is Status.ERROR
    assert "per-call timeout" in check(report, "fixture.call.transport").message


@pytest.mark.asyncio
async def test_total_timeout_is_enforced_and_keeps_partial_results() -> None:
    with gateway(call_delay=2.0) as (url, _):
        report = await smoke(
            url, limits={"per_call_timeout_seconds": 1, "total_timeout_seconds": 1}
        )
    assert report.status is Status.ERROR
    assert check(report, "lane.total_timeout").status is Status.ERROR
    assert report.steps[0].status is Status.PASS  # what finished is kept


@pytest.mark.asyncio
async def test_max_response_bytes_is_enforced() -> None:
    with gateway(pad_description=6000) as (url, _):
        report = await smoke(url, limits={"max_response_bytes": 4096})
    assert report.status is Status.ERROR
    assert any("body-size limit" in c.message for s in report.steps for c in s.checks)


@pytest.mark.asyncio
async def test_max_total_bytes_is_enforced() -> None:
    with gateway() as (url, _):
        report = await smoke(url, limits={"max_total_bytes": 2048, "max_response_bytes": 2048})
    assert report.status is Status.ERROR
    assert any(
        "max_total_bytes" in c.message or "body-size" in c.message
        for s in report.steps
        for c in s.checks
    )


# ---------------------------------------------------------------- redaction


@pytest.mark.parametrize(
    "scenario",
    [
        {},
        {"call_mode": "echo_token"},
        {"token_mode": "invalid_client"},
        {"call_mode": "wrong_value"},
    ],
)
@pytest.mark.asyncio
async def test_no_credential_appears_in_any_output(scenario: dict[str, Any]) -> None:
    with gateway(**scenario) as (url, _):
        report = await smoke(url)
    rendered = to_json(report) + to_junit(report) + to_human(report)
    assert_no_secret(rendered)
    assert not re.search(r"(?i)\b(bearer|basic)\s+(?!\[REDACTED\])[A-Za-z0-9+/=_.-]{12,}", rendered)


@pytest.mark.asyncio
async def test_leaked_token_in_fixture_response_is_scrubbed_from_failure_evidence() -> None:
    with gateway(call_mode="echo_token") as (url, _):
        report = await smoke(url)
    item = check(report, "fixture.expect.1")
    assert item.status is Status.FAIL
    assert fake.ACCESS_TOKEN not in json.dumps(item.evidence)
    assert "[REDACTED]" in item.evidence["actual"]


def test_url_query_strings_are_stripped_from_text() -> None:
    text = "see https://gw.example.net/mcp?api_key=SECRET&x=1#frag and http://127.0.0.1:9/p?q=1."
    cleaned = _strip_url_queries(text)
    assert "SECRET" not in cleaned and "?" not in cleaned and "#frag" not in cleaned
    assert "https://gw.example.net/mcp" in cleaned


@pytest.mark.asyncio
async def test_target_url_query_is_not_reported() -> None:
    config_doc = doc("http://127.0.0.1:1")
    config_doc["mcp_url"] = "https://gateway.example.com/mcp?api_key=SECRET-QUERY"
    report = await run_smoke(loads_config(json.dumps(config_doc)), environ=ENV)
    assert report.to_dict()["target"]["mcp_url"] == "https://gateway.example.com/mcp"
    assert "SECRET-QUERY" not in to_json(report) + to_junit(report) + to_human(report)


# ---------------------------------------------------------------- reports


@pytest.mark.asyncio
async def test_json_report_shape_and_identity_in_every_status() -> None:
    scenarios = [({}, {}), ({"token_mode": "invalid_client"}, {}), ({"call_mode": "wrong_value"}, {}),
                 ({"call_mode": "malformed"}, {}), ({}, {"env": {}})]  # fmt: skip
    seen = set()
    for behavior, kwargs in scenarios:
        with gateway(**behavior) as (url, _):
            report = await smoke(url, **kwargs)
        payload = json.loads(to_json(report))
        seen.add(payload["status"])
        assert payload["schema"] == "testmcpy.io/gateway-smoke-report/v1"
        assert payload["environment"] == "local-fake"
        assert payload["workspace"]["id"] == fake.CANARY_WORKSPACE_ID
        assert payload["workspace"]["name"] == fake.CANARY_WORKSPACE_NAME
        assert payload["exit_code"] == EXIT_CODES[Status(payload["status"])]
        assert [s["id"] for s in payload["steps"]] == [
            "protocol_auth",
            "tool_discovery",
            "fixture_read",
        ]
    assert seen == {"PASS", "BLOCKED", "FAIL", "ERROR"}


@pytest.mark.asyncio
async def test_junit_is_valid_and_never_reads_blocked_as_green() -> None:
    with gateway(token_mode="invalid_client") as (url, _):
        blocked = await smoke(url)
    suite = ET.fromstring(to_junit(blocked).encode())
    assert suite.tag == "testsuite"
    props = {p.get("name"): p.get("value") for p in suite.iter("property")}
    assert props["environment"] == "local-fake"
    assert props["workspace_id"] == fake.CANARY_WORKSPACE_ID
    assert props["status"] == "BLOCKED"
    errors = list(suite.iter("error"))
    assert errors and all(e.get("type") == "BLOCKED" for e in errors)
    assert int(suite.get("errors", "0")) == len(errors)
    assert len(suite.findall("testcase")) == int(suite.get("tests", "0"))
    assert suite.findall(".//skipped")  # unrun steps


@pytest.mark.asyncio
async def test_junit_failure_and_pass() -> None:
    with gateway(call_mode="wrong_value") as (url, _):
        failed = await smoke(url)
    suite = ET.fromstring(to_junit(failed).encode())
    assert int(suite.get("failures", "0")) == 1
    assert suite.find(".//failure").get("type") == "FAIL"
    with gateway() as (url, _):
        passed = await smoke(url)
    suite = ET.fromstring(to_junit(passed).encode())
    assert suite.get("failures") == "0" and suite.get("errors") == "0"


def test_status_precedence_and_pass_requires_every_step() -> None:
    assert worst([Status.PASS, Status.BLOCKED]) is Status.BLOCKED
    assert worst([Status.BLOCKED, Status.FAIL]) is Status.FAIL
    assert worst([Status.FAIL, Status.ERROR, Status.BLOCKED]) is Status.ERROR
    assert worst([Status.PASS, Status.PASS]) is Status.PASS
    # A step that never ran with no explanation is not a pass.
    assert worst([Status.PASS, Status.SKIPPED]) is Status.ERROR


# ---------------------------------------------------------------- assertions


@pytest.mark.parametrize(
    ("payload", "assertion", "ok"),
    [
        ({"a": {"b": [1, 2]}}, {"path": "a.b.1", "equals": 2}, True),
        ({"a": {"b": [1, 2]}}, {"path": "a.b.1", "equals": 3}, False),
        ({"a": 1}, {"path": "a", "equals": True}, False),  # bool is not 1
        ({"a": 1}, {"path": "a", "equals": 1.0}, True),
        ({"a": "x"}, {"path": "b", "exists": False}, True),
        ({"a": "x"}, {"path": "b", "equals": "x"}, False),
        ({"a": [1]}, {"path": "a", "type": "array"}, True),
        ({"a": 1}, {"path": "a", "type": "number"}, True),
        ({"a": True}, {"path": "a", "type": "integer"}, False),
        ({"a": ["x", "y"]}, {"path": "a", "contains": "y"}, True),
        ({"a": "hello"}, {"path": "a", "contains": "ell"}, True),
        ({"a": ["x"]}, {"path": "a", "min_length": 2}, False),
        ([{"id": 7}], {"path": "0.id", "equals": 7}, True),
    ],
)
def test_assertion_evaluation(payload: Any, assertion: dict[str, Any], ok: bool) -> None:
    from testmcpy.gateway_smoke.config import _assertion

    result, _, _ = evaluate_assertion(payload, _assertion(assertion, "x"))
    assert result is ok


# ---------------------------------------------------------------- config


def _load(**mutations: Any) -> Any:
    config_doc = doc("http://127.0.0.1:1")
    for dotted, value in mutations.items():
        node = config_doc
        *parents, leaf = dotted.split("__")
        for part in parents:
            node = node.setdefault(part, {})
        if value is None:
            node.pop(leaf, None)
        else:
            node[leaf] = value
    return loads_config(json.dumps(config_doc))


@pytest.mark.parametrize(
    ("mutations", "message"),
    [
        ({"surprise": 1}, "unknown field"),
        ({"schema": "other/v1"}, "unsupported schema"),
        ({"auth__client_secret": "a-literal-secret"}, "must be an object"),
        ({"auth__client_id": None}, "requires auth.client_id"),
        ({"fixture__read_only": None}, "read_only must be true"),
        ({"fixture__read_only": False}, "read_only must be true"),
        ({"fixture__tool": "delete_dashboard"}, "looks like a write"),
        ({"fixture__tool": "generateChart"}, "looks like a write"),
        ({"fixture__expect": []}, "at least one"),
        (
            {"fixture__arguments": {"workspace_id": "some-other-workspace"}},
            "must equal workspace.id",
        ),
        ({"limits__per_call_timeout_seconds": 90}, "must not exceed"),
        ({"limits__max_calls": 500}, "max_calls"),
        ({"workspace__name": None}, "workspace.name"),
        ({"environment": None}, "environment"),
        ({"auth__mode": "password"}, "auth.mode"),
    ],
)
def test_invalid_configs_are_rejected(mutations: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        _load(**mutations)


def test_dispatching_fixture_checks_the_dispatched_tool_name() -> None:
    dispatch = {
        "read_only": True,
        "tool": "call_tool",
        "inner_tool_argument": "tool_name",
        "arguments": {
            "workspace_id": fake.CANARY_WORKSPACE_ID,
            "tool_name": "get_workspace_catalog",
            "args": {},
        },
        "workspace_argument": "workspace_id",
        "expect": [{"path": "x", "exists": True}],
    }
    assert _load(fixture=dispatch).fixture.inner_tool_argument == "tool_name"
    bad = copy.deepcopy(dispatch)
    bad["arguments"]["tool_name"] = "update_dashboard"
    with pytest.raises(ConfigError, match="looks like a write"):
        _load(fixture=bad)


def test_config_has_no_way_to_carry_a_token() -> None:
    for key in ("token", "access_token_value", "password", "authorization"):
        with pytest.raises(ConfigError, match="unknown field"):
            _load(**{f"auth__{key}": "abc"})


# ---------------------------------------------------------------- CLI


def test_cli_has_no_credential_flags(capsys: pytest.CaptureFixture[str]) -> None:
    for flag in ("--token", "--access-token", "--client-secret", "--password", "--authorization"):
        with pytest.raises(SystemExit) as exc:
            smoke_cli.main(["run", "--config", "x.yaml", flag, "abc"])
        assert exc.value.code == 2
    capsys.readouterr()


def test_cli_validate_example_and_blocked_run_of_example(tmp_path: Path) -> None:
    assert smoke_cli.main(["validate", "--config", str(EXAMPLE)]) == 0
    out, junit = tmp_path / "r.json", tmp_path / "r.xml"
    code = smoke_cli.main(
        ["run", "--config", str(EXAMPLE), "--format", "json", "--output", str(out),
         "--junit", str(junit)]
    )  # fmt: skip
    assert code == 3
    payload = json.loads(out.read_text())
    assert payload["status"] == "BLOCKED" and payload["usage"]["calls"] == 0
    assert payload["environment"] == "REPLACE_ME-environment-label"
    ET.fromstring(junit.read_bytes())


def test_cli_missing_and_invalid_config_are_blocked_with_best_effort_identity(
    tmp_path: Path,
) -> None:
    out = tmp_path / "r.json"
    assert smoke_cli.main(["run", "--config", str(tmp_path / "nope.yaml"), "--format", "json",
                           "--output", str(out)]) == 3  # fmt: skip
    assert json.loads(out.read_text())["status"] == "BLOCKED"
    broken = tmp_path / "broken.yaml"
    broken.write_text(
        "schema: testmcpy.io/gateway-smoke/v1\nenvironment: sandbox\n"
        "workspace: {id: ws-1, name: canary}\nbogus: true\n"
    )
    assert (
        smoke_cli.main(["run", "--config", str(broken), "--format", "json", "--output", str(out)])
        == 3
    )
    payload = json.loads(out.read_text())
    assert (payload["environment"], payload["workspace"]) == (
        "sandbox",
        {"id": "ws-1", "name": "canary"},
    )
    assert smoke_cli.main(["validate", "--config", str(broken)]) == 3


def test_cli_identity_expectations_block_a_mismatched_config(tmp_path: Path) -> None:
    config = tmp_path / "c.yaml"
    config.write_text(json.dumps(doc("http://127.0.0.1:1")))
    out = tmp_path / "r.json"
    code = smoke_cli.main(["run", "--config", str(config), "--format", "json", "--output", str(out),
                           "--expect-environment", "production"])  # fmt: skip
    payload = json.loads(out.read_text())
    assert code == 3 and payload["status"] == "BLOCKED" and payload["usage"]["calls"] == 0
    assert "--expect-environment" in payload["steps"][0]["checks"][0]["message"]


def test_cli_end_to_end_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMOKE_CLIENT_SECRET", CLIENT_SECRET)
    with gateway() as (url, _):
        config = tmp_path / "c.yaml"
        config.write_text(json.dumps(doc(url)))
        out, junit = tmp_path / "r.json", tmp_path / "r.xml"
        code = smoke_cli.main(["run", "--config", str(config), "--format", "json",
                               "--output", str(out), "--junit", str(junit),
                               "--expect-environment", "local-fake",
                               "--expect-workspace-id", fake.CANARY_WORKSPACE_ID])  # fmt: skip
    assert code == 0 and json.loads(out.read_text())["status"] == "PASS"
    assert_no_secret(out.read_text() + junit.read_text())


# ---------------------------------------------------------------- invariants


def test_lane_imports_no_llm_client() -> None:
    package = REPO_ROOT / "testmcpy/gateway_smoke"
    forbidden = re.compile(r"\b(anthropic|openai|litellm|ollama|google\.genai|claude_agent_sdk)\b")
    for source in package.glob("*.py"):
        assert not forbidden.search(source.read_text()), source.name


def test_lane_has_no_write_path() -> None:
    """The only MCP methods the lane can send are the four it needs."""
    sources = "".join(p.read_text() for p in (REPO_ROOT / "testmcpy/gateway_smoke").glob("*.py"))
    methods = set(
        re.findall(r'"(tools/\w+|initialize|notifications/\w+|resources/\w+|prompts/\w+)"', sources)
    )
    assert methods == {"initialize", "notifications/initialized", "tools/list", "tools/call"}


def test_example_config_contains_only_placeholders() -> None:
    text = EXAMPLE.read_text()
    assert "REPLACE_ME" in text
    assert not re.search(r"preset\.(io|zone)|manage\.app", text)
    config = loads_config(text)
    assert config.placeholders()


def test_message_text_and_urls_are_scrubbed_before_emission() -> None:
    from testmcpy_oauth_probe.secrets import SecretRegistry

    from testmcpy.gateway_smoke.models import Check
    from testmcpy.gateway_smoke.runner import _sanitize, blocked_report

    report = blocked_report("missing.yaml", "x")
    registry = SecretRegistry({})
    registry.register("registered-secret-value-123")
    report.steps[0].checks.append(
        Check(
            id="t",
            status=Status.ERROR,
            message="boom registered-secret-value-123 at https://h.example.net/p?token=Q#f",
            evidence={
                "nested": {"note": "again registered-secret-value-123"},
                "authorization": "x",
            },
        )
    )
    clean = _sanitize(report, registry)
    rendered = to_json(clean)
    assert "registered-secret-value-123" not in rendered
    assert "token=Q" not in rendered and "#f" not in rendered
    assert clean.steps[0].checks[-1].evidence["authorization"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_truncated_catalogue_is_named_as_the_reason_a_fixture_tool_was_not_seen() -> None:
    with gateway(page_size=1) as (url, behavior):
        report = await smoke(url, discovery={"max_pages": 1})
    item = check(report, "fixture.tool.advertised")
    assert item.status is Status.FAIL and "page cap" in item.message
    assert behavior.tool_calls == []


def test_unwritable_output_is_error_not_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "c.yaml"
    config.write_text(json.dumps(doc("http://127.0.0.1:1")))
    code = smoke_cli.main(
        ["run", "--config", str(config), "--output", str(tmp_path / "no-such-dir" / "r.json")]
    )
    assert code == 2
