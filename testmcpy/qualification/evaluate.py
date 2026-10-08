"""Aggregate task runs and evaluate them against the pre-registered budgets."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from testmcpy.qualification.runner import TaskRun


def _pct(values: Sequence[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(pct * len(ordered)) - 1))]


def aggregate(
    runs: list[TaskRun], policies: tuple[str, ...]
) -> dict[tuple[str, str], dict[str, Any]]:
    """Per (catalog, surface) metrics."""
    groups: dict[tuple[str, str], list[TaskRun]] = defaultdict(list)
    for r in runs:
        groups[(r.catalog, r.surface)].append(r)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for key, rs in groups.items():
        totals = [r.tokens["total"] for r in rs]
        lat = [r.latency_ms for r in rs]
        disc = [r.discovery_round_trips for r in rs]
        positive = sum(r.positive_ops for r in rs)
        ops = sum(r.op_calls for r in rs)
        reference = next((r for r in rs if r.task == "chart-find"), rs[0])
        approvals: dict[str, dict[str, float]] = {}
        for p in policies:
            reads = [r.approvals[p] for r in rs if r.task not in _WRITE_TASKS]
            writes = [r.approvals[p] / _WRITE_OPS[r.task] for r in rs if r.task in _WRITE_OPS]
            approvals[p] = {
                "read_only_task_mean": round(statistics.mean(reads), 3) if reads else 0.0,
                "write_task_per_write_op": round(statistics.mean(writes), 3) if writes else 0.0,
            }
        out[key] = {
            "tasks": len(rs),
            "initial_tokens": reference.tokens["initial"],
            "initial_tokens_max": max(r.tokens["initial"] for r in rs),
            "task_total_tokens": {
                "median": statistics.median(totals),
                "p90": _pct(totals, 0.9),
                "max": max(totals),
            },
            "latency_ms": {
                "median": round(statistics.median(lat), 2),
                "p95": round(_pct(lat, 0.95), 2),
            },
            "discovery_round_trips": {"median": statistics.median(disc), "max": max(disc)},
            "accuracy_scripted": round(sum(r.success for r in rs) / len(rs), 4),
            "failed_tasks": [r.task for r in rs if not r.success],
            "missing_tool_rate": round(sum(r.missing_ops for r in rs) / positive, 4)
            if positive
            else 0.0,
            "positive_ops": positive,
            "arg_failure_rate": round(sum(r.arg_failures for r in rs) / ops, 4) if ops else 0.0,
            "op_calls": ops,
            "approvals": approvals,
            "per_task": {
                r.task: {
                    "success": r.success,
                    "initial": r.tokens["initial"],
                    "total": r.tokens["total"],
                    "discovery_rt": r.discovery_round_trips,
                    "latency_ms": r.latency_ms,
                    "approvals": r.approvals,
                }
                for r in rs
            },
        }
    return out


# Tasks whose oracle expects a write, and how many write operations each performs.
_WRITE_OPS = {"chart-create": 1, "write-approval-write": 1}
_WRITE_TASKS = frozenset(_WRITE_OPS)


def load_budgets(path: str | Path) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(Path(path).read_text())
    return loaded


def _verdict(
    bid: str,
    surface: str,
    catalog: str,
    value: Any,
    hard: Any,
    target: Any,
    ok: bool,
    target_met: bool,
    gating: bool,
    note: str = "",
    evidence: str = "measured",
) -> dict[str, Any]:
    return {
        "budget": bid,
        "surface": surface,
        "catalog": catalog,
        "value": value,
        "hard_limit": hard,
        "target": target,
        "status": ("pass" if ok else "FAIL") if gating else ("would-pass" if ok else "would-fail"),
        "target_met": target_met,
        "gating": gating,
        "evidence": evidence,
        "note": note,
    }


def evaluate(
    budgets: dict[str, Any],
    metrics: dict[tuple[str, str], dict[str, Any]],
    catalog_stats: dict[str, dict[str, Any]],
    pagination: dict[str, list[dict[str, Any]]],
    leaks: int,
    fidelity: dict[str, Any] | None,
    llm_runs: bool = False,
) -> list[dict[str, Any]]:
    by_id = {b["id"].split("-", 1)[0]: b for b in budgets["budgets"]}
    verdicts: list[dict[str, Any]] = []

    def b(bid: str) -> dict[str, Any]:
        budget: dict[str, Any] = by_id[bid]
        return budget

    for (catalog, surface), m in sorted(metrics.items()):
        generic = metrics.get((catalog, "generic"))
        # B01
        bd = b("B01")
        v = m["initial_tokens"]
        verdicts.append(
            _verdict(
                bd["id"],
                surface,
                catalog,
                v,
                bd["hard_limit"],
                bd["target"],
                v <= bd["hard_limit"],
                v <= bd["target"],
                bd["gating"],
                f"max across tasks {m['initial_tokens_max']}",
            )
        )
        # B02 (native only)
        if surface != "generic":
            bd = b("B02")
            st = catalog_stats[catalog]["native"]
            vals = {"median": st["median"], "p95": st["p95"], "max": st["max"]}
            ok = all(vals[k] <= bd["hard_limit"][k] for k in vals)
            tm = all(vals[k] <= bd["target"][k] for k in vals)
            verdicts.append(
                _verdict(
                    bd["id"],
                    surface,
                    catalog,
                    vals,
                    bd["hard_limit"],
                    bd["target"],
                    ok,
                    tm,
                    bd["gating"],
                )
            )
        # B03
        bd = b("B03")
        t = m["task_total_tokens"]
        vals = {"median": t["median"], "p90": t["p90"]}
        ok = all(vals[k] <= bd["hard_limit"][k] for k in vals)
        tm = all(vals[k] <= bd["target"][k] for k in vals)
        note = ""
        if surface != "generic" and generic:
            ratio = t["median"] / generic["task_total_tokens"]["median"]
            rel_ok = ratio <= 1.25
            note = f"median is {ratio:.2f}x the generic baseline (limit 1.25x; no accuracy gain: scripted accuracy equal)"
            ok = ok and rel_ok
        verdicts.append(
            _verdict(
                bd["id"],
                surface,
                catalog,
                vals,
                bd["hard_limit"],
                bd["target"],
                ok,
                tm,
                bd["gating"],
                note,
            )
        )
        # B04
        bd = b("B04")
        lat = m["latency_ms"]
        ok = lat["median"] <= bd["hard_limit"]["median"] and lat["p95"] <= bd["hard_limit"]["p95"]
        tm = lat["median"] <= bd["target"]["median"] and lat["p95"] <= bd["target"]["p95"]
        note = "in-process fixture; protocol overhead only, not model or network time"
        if surface != "generic" and generic:
            rel = lat["p95"] <= generic["latency_ms"]["p95"] + 250
            ok = ok and rel
            note += f"; p95 delta vs generic {lat['p95'] - generic['latency_ms']['p95']:+.1f} ms (limit +250)"
        verdicts.append(
            _verdict(
                bd["id"],
                surface,
                catalog,
                lat,
                bd["hard_limit"],
                bd["target"],
                ok,
                tm,
                bd["gating"],
                note,
            )
        )
        # B05
        bd = b("B05")
        d = m["discovery_round_trips"]
        ok = d["median"] <= bd["hard_limit"]["median"] and d["max"] <= bd["hard_limit"]["max"]
        tm = d["median"] <= bd["target"]["median"] and d["max"] <= bd["target"]["max"]
        verdicts.append(
            _verdict(
                bd["id"],
                surface,
                catalog,
                d,
                bd["hard_limit"],
                bd["target"],
                ok,
                tm,
                bd["gating"],
                "native_deferred discovery is simulated" if surface == "native_deferred" else "",
                "simulated" if surface == "native_deferred" else "measured",
            )
        )
        # B06
        bd = b("B06")
        acc = m["accuracy_scripted"]
        verdicts.append(
            _verdict(
                bd["id"],
                surface,
                catalog,
                {"scripted": acc, "llm_read_tasks": "BLOCKED"},
                bd["hard_limit"],
                bd["target"],
                acc >= bd["hard_limit"]["scripted"],
                acc >= bd["target"]["scripted"],
                bd["gating"],
                "scripted reference agent; LLM-driven accuracy is blocked" if not llm_runs else "",
                "measured",
            )
        )
        # B07
        bd = b("B07")
        mr = m["missing_tool_rate"]
        verdicts.append(
            _verdict(
                bd["id"],
                surface,
                catalog,
                mr,
                bd["hard_limit"],
                bd["target"],
                mr <= bd["hard_limit"],
                mr <= bd["target"],
                bd["gating"],
                f"{m['positive_ops']} positive operations",
            )
        )
        # B08
        bd = b("B08")
        af = m["arg_failure_rate"]
        ok = af <= bd["hard_limit"]
        note = f"{m['op_calls']} schema-conforming first-attempt calls; malformed-argument probes reported separately"
        verdicts.append(
            _verdict(
                bd["id"],
                surface,
                catalog,
                af,
                bd["hard_limit"],
                bd["target"],
                ok,
                af <= bd["target"],
                bd["gating"],
                note,
            )
        )
        # B09
        bd = b("B09")
        ap = m["approvals"]["honours_annotations"]
        ok = (
            ap["read_only_task_mean"] <= bd["hard_limit"]["read_only_task"]
            and ap["write_task_per_write_op"] <= bd["hard_limit"]["write_task_per_write_op"]
        )
        verdicts.append(
            _verdict(
                bd["id"],
                surface,
                catalog,
                ap,
                bd["hard_limit"],
                bd["target"],
                ok,
                ok,
                bd["gating"],
                "policy: honours_annotations; other policies in the report",
                "simulated",
            )
        )
        # B10
        if surface != "generic":
            bd = b("B10")
            comp = min(r["completeness"] for r in pagination[catalog])
            verdicts.append(
                _verdict(
                    bd["id"],
                    surface,
                    catalog,
                    comp,
                    bd["hard_limit"],
                    bd["target"],
                    comp >= bd["hard_limit"],
                    comp >= bd["target"],
                    bd["gating"],
                    f"page sizes {[r['page_size'] for r in pagination[catalog]]}",
                )
            )
        # B11
        bd = b("B11")
        verdicts.append(
            _verdict(
                bd["id"],
                surface,
                catalog,
                leaks,
                bd["hard_limit"],
                bd["target"],
                leaks <= bd["hard_limit"],
                leaks <= bd["target"],
                bd["gating"],
                "fixture probe matrix, both server surfaces",
            )
        )
        # B12
        bd = b("B12")
        if surface == "generic" and fidelity and fidelity.get("fraction") is not None:
            fr = fidelity["fraction"]
            bad = [
                c["probe"]
                for c in fidelity["compared"]
                if not (c["flags_identical"] and c["text_identical"])
            ]
            verdicts.append(
                _verdict(
                    bd["id"],
                    surface,
                    catalog,
                    fr,
                    bd["hard_limit"],
                    bd["target"],
                    fr >= bd["hard_limit"],
                    fr >= bd["target"],
                    bd["gating"],
                    f"real Superset app; differing probes: {bad}",
                )
            )
        elif surface != "generic":
            verdicts.append(
                _verdict(
                    bd["id"],
                    surface,
                    catalog,
                    1.0,
                    bd["hard_limit"],
                    bd["target"],
                    True,
                    True,
                    bd["gating"],
                    "reference surface: no dispatcher between client and tool",
                    "by-construction",
                )
            )
    return verdicts
