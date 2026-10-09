"""Client approval-policy models (SIMULATED, never observed client behaviour).

A real client decides for itself whether to prompt; annotations are advisory
hints from the server and do not override that decision. These models answer
"how many prompts would a client that chooses policy X raise for these calls?"
and nothing more. Observed behaviour belongs in the client matrix.

MCP spec defaults apply when an annotation is absent: ``readOnlyHint=false``,
``destructiveHint=true``, ``openWorldHint=true``. A tool with no annotations
is therefore indistinguishable from a destructive one, which is how a generic
dispatcher makes every read look like a write.
"""

from __future__ import annotations

from typing import Any

POLICIES = {
    "honours_annotations": "auto-approves tools annotated readOnlyHint=true and "
    "openWorldHint!=true; prompts for everything else (including unannotated tools)",
    "prompts_on_everything": "prompts for every tool call",
    "untrusted_server": "prompts for every tool call (server not on an allow-list)",
}

_SPEC_DEFAULTS = {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": True}


def effective_annotations(annotations: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(_SPEC_DEFAULTS)
    merged.update({k: v for k, v in (annotations or {}).items() if k in _SPEC_DEFAULTS})
    return merged


def needs_prompt(policy: str, annotations: dict[str, Any] | None) -> bool:
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    if policy == "honours_annotations":
        eff = effective_annotations(annotations)
        return not (eff["readOnlyHint"] is True and eff["openWorldHint"] is not True)
    return True


def count_prompts(policy: str, called_tools: list[dict[str, Any] | None]) -> int:
    """``called_tools`` are the surface tool definitions actually invoked, in order."""
    return sum(1 for t in called_tools if needs_prompt(policy, (t or {}).get("annotations")))
