"""Human, JSON, JSONL, and JUnit reporters for the versioned result model."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

from testmcpy_oauth_probe.models import CheckStatus, RunReport

_INVALID_XML_10 = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\uFFFE\uFFFF]")


def _xml_text(value: object) -> str:
    return _INVALID_XML_10.sub("�", str(value))


def to_json(report: RunReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"


def to_jsonl(report: RunReport) -> str:
    lines = []
    for target in report.reports:
        lines.append(
            json.dumps(
                {
                    "schema": report.schema,
                    "run": {
                        "id": report.run_id,
                        "tool_version": report.tool_version,
                        "started_at": report.started_at,
                        "duration_ms": report.duration_ms,
                    },
                    "targets": [target.to_dict()],
                },
                sort_keys=True,
            )
        )
    return "\n".join(lines) + ("\n" if lines else "")


def to_human(report: RunReport) -> str:
    lines = [
        f"OAuth/MCP probe run {report.run_id} ({report.tool_version})",
        "This is an interoperability/policy report, not a formal compliance certification.",
    ]
    for target in report.reports:
        correlation = ", ".join(
            value
            for value in (
                f"service={target.correlation.service}" if target.correlation.service else "",
                f"region={target.correlation.region}" if target.correlation.region else "",
                f"revision={target.correlation.revision}" if target.correlation.revision else "",
                f"deployment={target.correlation.deployment_id}"
                if target.correlation.deployment_id
                else "",
            )
            if value
        )
        lines.append(f"\n[{target.target_id}] {correlation}".rstrip())
        for check in target.checks:
            status = check.status.value.upper().ljust(5)
            http = f" HTTP {check.http_status}" if check.http_status is not None else ""
            lines.append(f"  {status} {check.id}{http}: {check.message}")
        summary = " ".join(f"{key}={value}" for key, value in target.summary.items())
        lines.append(f"  summary: {summary}")
    return "\n".join(lines) + "\n"


def to_junit(report: RunReport) -> str:
    checks = [(target, check) for target in report.reports for check in target.checks]
    suite = ET.Element(
        "testsuite",
        name="testmcpy-oauth-probe",
        tests=str(len(checks)),
        failures=str(sum(check.status is CheckStatus.FAIL for _, check in checks)),
        errors=str(sum(check.status is CheckStatus.ERROR for _, check in checks)),
        skipped=str(sum(check.status is CheckStatus.SKIP for _, check in checks)),
        time=f"{report.duration_ms / 1000:.3f}",
    )
    properties = ET.SubElement(suite, "properties")
    ET.SubElement(properties, "property", name="schema", value=_xml_text(report.schema))
    ET.SubElement(properties, "property", name="run_id", value=_xml_text(report.run_id))
    ET.SubElement(properties, "property", name="tool_version", value=_xml_text(report.tool_version))
    for target, check in checks:
        case = ET.SubElement(
            suite,
            "testcase",
            name=_xml_text(f"{target.target_id}::{check.id}"),
            classname=_xml_text(f"oauth_probe.{check.stage}"),
            time=f"{check.duration_ms / 1000:.3f}",
        )
        case_properties = ET.SubElement(case, "properties")
        for name, value in (
            ("target", target.target_id),
            ("service", target.correlation.service),
            ("region", target.correlation.region),
            ("revision", target.correlation.revision),
            ("deployment_id", target.correlation.deployment_id),
            ("spec_profile", target.spec_profile),
            ("http_status", check.http_status),
        ):
            if value is not None:
                ET.SubElement(case_properties, "property", name=name, value=_xml_text(value))
        if check.status is CheckStatus.SKIP:
            ET.SubElement(case, "skipped", message=_xml_text(check.message))
        elif check.status is CheckStatus.FAIL:
            failure = ET.SubElement(case, "failure", message=_xml_text(check.message))
            failure.text = _xml_text(check.message)
        elif check.status is CheckStatus.ERROR:
            error = ET.SubElement(case, "error", message=_xml_text(check.message))
            error.text = _xml_text(check.message)
        output = ET.SubElement(case, "system-out")
        output.text = _xml_text(json.dumps(check.evidence, sort_keys=True))
    ET.indent(suite)
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"
