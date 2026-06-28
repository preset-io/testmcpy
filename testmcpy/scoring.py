"""Single source of truth for test scoring.

A test's score is built in two layers:

1. **Base score** — the simple mean of every evaluator's 0..1 score.
2. **False-positive penalty** — a multiplicative penalty for tool calls the
   model made that were *not* one of the test's expected ("primary") tools.

Expected tools are declared by ``was_tool_called:`` / ``was_mcp_tool_called:``
evaluators (the suffix after the colon names the tool). **All** such evaluators
are honoured, so a test may legitimately expect more than one tool — historically
only the first was, which wrongly penalised multi-tool tests.

    false_positive_rate = (total_calls - primary_calls) / total_calls
    final = base * max(0.5, 1 - false_positive_rate)

The 0.5 floor means the false-positive penalty can at most halve the score.

Relationship to the ``unnecessary_tool_calls`` evaluator
--------------------------------------------------------
``unnecessary_tool_calls`` penalises *duplicate* calls (same tool + args) and
already feeds into the base mean as an ordinary evaluator. The false-positive
penalty here is about *non-primary* tools. Duplicate calls of the primary tool
keep the false-positive rate low (they still count as primary calls), so the two
penalties target disjoint problems and are applied independently — there is no
double counting to guard against. (An earlier version skipped the false-positive
penalty entirely whenever ``unnecessary_tool_calls`` failed, which silently
dropped the non-primary penalty.)

Manual false positives
-----------------------
When a human marks a result as a false positive (``manual_false_positive``), we
apply the same floor multiplier the worst automatic penalty hits. This is a
deliberate product rule — tune ``MANUAL_FP_MULTIPLIER`` to change it.

This module is pure (no DB, no IO) so the write path (runner + storage) and the
read paths (results / analytics routers) all explain the score the same way.
"""

from __future__ import annotations

from typing import Any

# The false-positive penalty can at most halve a score.
PENALTY_FLOOR = 0.5
# Multiplier applied when a human flags a result as a false positive.
MANUAL_FP_MULTIPLIER = 0.5

_PRIMARY_TOOL_PREFIXES = ("was_tool_called:", "was_mcp_tool_called:")


def real_tool_name(tool_use: dict[str, Any]) -> str:
    """Extract the canonical tool name from a tool_use dict.

    Handles three patterns:
    - Gateway: ``mcp__ns__call_tool`` + ``arguments.name="my_tool"`` → ``my_tool``
    - Direct prefixed: ``mcp__ns__my_tool`` → ``my_tool``
    - Plain: ``my_tool`` → ``my_tool``

    Recurses so a gateway inner name that is itself prefixed is also normalized.
    Falls back to ``tool_use["tool_name"]`` for alternate payload shapes.
    """
    name = str(tool_use.get("name") or tool_use.get("tool_name") or "")
    args = tool_use.get("arguments", {}) or {}

    if name.endswith("__call_tool") or name == "call_tool":
        inner = args.get("name") or args.get("tool_name") or ""
        if inner:
            return real_tool_name({"name": inner, "arguments": {}})
        return "call_tool"

    if "__" in name:
        return name.split("__")[-1]

    return name


def primary_tools_from_evaluations(evaluations: list[dict[str, Any]] | None) -> list[str]:
    """Canonical names of every tool the test declared as expected.

    Reads *all* ``was_tool_called:`` / ``was_mcp_tool_called:`` evaluators (the
    name after the colon), normalising any MCP prefix on the declared name.
    """
    tools: list[str] = []
    for ev in evaluations or []:
        ev_name = ev.get("evaluator", "") or ev.get("name", "")
        for prefix in _PRIMARY_TOOL_PREFIXES:
            if ev_name.startswith(prefix):
                raw = ev_name.split(":", 1)[1]
                tools.append(real_tool_name({"name": raw}))
                break
    # De-dupe while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for t in tools:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered


def compute_tool_call_breakdown(
    tool_uses: list[dict[str, Any]] | None, evaluations: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """Tool-call counts and the false-positive rate for one result.

    With no expected tool declared, nothing can be "extra", so the rate is 0.
    """
    counts: dict[str, int] = {}
    for tu in tool_uses or []:
        name = real_tool_name(tu)
        counts[name] = counts.get(name, 0) + 1

    total_calls = sum(counts.values())
    primary_tools = primary_tools_from_evaluations(evaluations)
    primary_set = set(primary_tools)

    if primary_set:
        primary_calls = sum(c for t, c in counts.items() if t in primary_set)
    else:
        primary_calls = total_calls  # no expected tool → nothing is unexpected

    false_positive_calls = total_calls - primary_calls
    false_positive_rate = (false_positive_calls / total_calls) if total_calls > 0 else 0.0

    return {
        "tool_call_counts": counts,
        "primary_tools": primary_tools,
        "total_calls": total_calls,
        "primary_calls": primary_calls,
        "false_positive_calls": false_positive_calls,
        "false_positive_rate": false_positive_rate,
    }


def compute_score_breakdown(
    base_score: float,
    evaluations: list[dict[str, Any]] | None,
    tool_uses: list[dict[str, Any]] | None = None,
    manual_false_positive: bool = False,
    override_final_score: float | None = None,
) -> dict[str, Any]:
    """Build a fully structured, UI-ready explanation of a test's score.

    ``base_score`` is the pre-penalty mean of evaluator scores. The returned
    ``final_score`` applies the false-positive (or manual) penalty.

    ``override_final_score`` is for the *read* path: historical rows were scored
    under older logic, so callers pass the already-stored final score and we
    derive the penalty multiplier from it (``final / base``) instead of
    recomputing — keeping the displayed breakdown consistent with the stored
    headline number. Live scoring leaves it ``None``.
    """
    evaluations = evaluations or []
    n = len(evaluations)
    weight = (1.0 / n) if n else 0.0
    evaluator_breakdown = [
        {
            "name": ev.get("evaluator") or ev.get("name") or "unknown",
            "score": ev.get("score", 0.0),
            "passed": bool(ev.get("passed", False)),
            "weight": weight,
        }
        for ev in evaluations
    ]

    tb = compute_tool_call_breakdown(tool_uses, evaluations)
    fp_rate = tb["false_positive_rate"]

    if override_final_score is not None:
        final_score = override_final_score
        multiplier = (final_score / base_score) if base_score > 0 else 1.0
        if manual_false_positive:
            penalty_source = "manual"
        elif multiplier < 0.999:
            penalty_source = "false_positive"
        else:
            penalty_source = None
    else:
        if manual_false_positive:
            multiplier = MANUAL_FP_MULTIPLIER
            penalty_source = "manual"
        elif fp_rate > 0:
            multiplier = max(PENALTY_FLOOR, 1.0 - fp_rate)
            penalty_source = "false_positive"
        else:
            multiplier = 1.0
            penalty_source = None
        final_score = base_score * multiplier

    factors: list[dict[str, Any]] = [
        {
            "label": "Base score",
            "value": round(base_score, 4),
            "detail": f"mean of {n} evaluator score{'s' if n != 1 else ''}",
        }
    ]

    if penalty_source == "false_positive":
        primary_set = set(tb["primary_tools"])
        unexpected = {t: c for t, c in tb["tool_call_counts"].items() if t not in primary_set}
        expected_label = (
            f" (expected: {', '.join(tb['primary_tools'])})" if tb["primary_tools"] else ""
        )
        unexpected_label = (
            "; unexpected: " + ", ".join(f"{t}×{c}" for t, c in unexpected.items())
            if unexpected
            else ""
        )
        factors.append(
            {
                "label": "False-positive tool-call penalty",
                "delta": round(final_score - base_score, 4),
                "multiplier": round(multiplier, 4),
                "detail": (
                    f"{tb['false_positive_calls']} of {tb['total_calls']} tool calls were "
                    f"not the expected tool{expected_label}{unexpected_label}"
                ),
            }
        )
    elif penalty_source == "manual":
        factors.append(
            {
                "label": "Manually marked false positive",
                "delta": round(final_score - base_score, 4),
                "multiplier": round(multiplier, 4),
                "detail": "A reviewer flagged this result as a false positive.",
            }
        )

    return {
        "base_score": round(base_score, 4),
        "evaluator_breakdown": evaluator_breakdown,
        "tool_call_counts": tb["tool_call_counts"],
        "primary_tools": tb["primary_tools"],
        "total_calls": tb["total_calls"],
        "primary_calls": tb["primary_calls"],
        "false_positive_calls": tb["false_positive_calls"],
        "false_positive_rate": round(fp_rate, 4),
        "penalty_multiplier": round(multiplier, 4),
        "penalty_source": penalty_source,
        "manual_false_positive": bool(manual_false_positive),
        "final_score": round(final_score, 4),
        "factors": factors,
    }
