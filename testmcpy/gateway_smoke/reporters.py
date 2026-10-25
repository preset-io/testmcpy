"""Human, JSON and JUnit XML renderings of a smoke report."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

from testmcpy.gateway_smoke.models import SmokeReport, Status

_INVALID_XML_10 = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F￾￿]")


def _xml_text(value: object) -> str:
    return _INVALID_XML_10.sub("�", str(value))


def to_json(report: SmokeReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"


def to_human(report: SmokeReport) -> str:
    lines = [
        f"gateway smoke {report.run_id} ({report.tool_version})",
        f"environment: {report.environment}",
        f"workspace:   {report.workspace_name} ({report.workspace_id})",
        f"target:      {report.mcp_url}",
        f"STATUS:      {report.status.value}  exit={report.exit_code}  {report.reason}",
        "",
    ]
    for step in report.steps:
        lines.append(f"[{step.status.value}] {step.id} - {step.title}")
        if step.skipped_reason and not step.checks:
            lines.append(f"    skipped: {step.skipped_reason}")
        for check in step.checks:
            http = f" HTTP {check.http_status}" if check.http_status is not None else ""
            lines.append(f"    {check.status.value:<7} {check.id}{http}: {check.message}")
    usage = report.usage
    lines.append("")
    lines.append(
        f"calls={usage['calls']}/{report.limits['max_calls']} bytes={usage['bytes']} "
        f"elapsed_ms={usage['elapsed_ms']} (no LLM calls, no writes)"
    )
    return "\n".join(lines) + "\n"


def to_junit(report: SmokeReport) -> str:
    checks = [(step, check) for step in report.steps for check in step.checks]
    skipped_steps = [step for step in report.steps if step.skipped_reason and not step.checks]
    cases = len(checks) + len(skipped_steps)

    def count(*statuses: Status) -> int:
        return sum(check.status in statuses for _, check in checks)

    suite = ET.Element(
        "testsuite",
        name="testmcpy-gateway-smoke",
        tests=str(cases),
        failures=str(count(Status.FAIL)),
        # BLOCKED is reported as a JUnit error so CI can never read it as green.
        errors=str(count(Status.ERROR, Status.BLOCKED)),
        skipped=str(len(skipped_steps)),
        time=f"{report.duration_ms / 1000:.3f}",
    )
    properties = ET.SubElement(suite, "properties")
    for name, value in (
        ("schema", report.to_dict()["schema"]),
        ("run_id", report.run_id),
        ("tool_version", report.tool_version),
        ("status", report.status.value),
        ("environment", report.environment),
        ("workspace_id", report.workspace_id),
        ("workspace_name", report.workspace_name),
        ("target", report.mcp_url),
    ):
        if value is not None:
            ET.SubElement(properties, "property", name=name, value=_xml_text(value))
    prefix = f"{report.environment}/{report.workspace_name}"
    for step, check in checks:
        case = ET.SubElement(
            suite,
            "testcase",
            name=_xml_text(f"{prefix}::{step.id}::{check.id}"),
            classname=_xml_text(f"gateway_smoke.{step.id}"),
            time=f"{check.duration_ms / 1000:.3f}",
        )
        if check.status is Status.FAIL:
            node = ET.SubElement(case, "failure", type="FAIL", message=_xml_text(check.message))
            node.text = _xml_text(check.message)
        elif check.status in (Status.ERROR, Status.BLOCKED):
            node = ET.SubElement(
                case, "error", type=check.status.value, message=_xml_text(check.message)
            )
            node.text = _xml_text(check.message)
        output = ET.SubElement(case, "system-out")
        output.text = _xml_text(json.dumps(check.evidence, sort_keys=True))
    for step in skipped_steps:
        case = ET.SubElement(
            suite,
            "testcase",
            name=_xml_text(f"{prefix}::{step.id}"),
            classname=_xml_text(f"gateway_smoke.{step.id}"),
            time="0.000",
        )
        ET.SubElement(case, "skipped", message=_xml_text(step.skipped_reason))
    ET.indent(suite)
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"
