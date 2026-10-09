"""Token accounting for tool definitions and tool-plane traffic.

Counting uses tiktoken ``o200k_base`` (the tokenizer pinned in
``budgets.yaml``). When tiktoken or its vocabulary is unavailable the module
falls back to ``ceil(bytes / 4)`` and reports ``estimator == "bytes/4"`` so a
number is never presented as more exact than it is.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Iterable
from typing import Any

_ENCODER: Any = None
_ESTIMATOR = "unset"


def _load() -> None:
    global _ENCODER, _ESTIMATOR
    if _ESTIMATOR != "unset":
        return
    try:
        import tiktoken

        _ENCODER = tiktoken.get_encoding("o200k_base")
        _ESTIMATOR = "tiktoken:o200k_base"
    except Exception:  # missing package or no cached/downloadable vocabulary
        _ENCODER = None
        _ESTIMATOR = "bytes/4"


def estimator() -> str:
    _load()
    return _ESTIMATOR


def compact_json(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def count_tokens(text: str) -> int:
    _load()
    if _ENCODER is not None:
        return len(_ENCODER.encode(text, disallowed_special=()))
    return math.ceil(len(text.encode("utf-8")) / 4)


def tool_definition(tool: dict[str, Any]) -> dict[str, Any]:
    """The model-visible shape of one MCP tool (annotations/title are not forwarded)."""
    return {
        "type": "function",
        "name": tool["name"],
        "description": tool.get("description", "") or "",
        "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}},
    }


def tool_tokens(tool: dict[str, Any]) -> int:
    return count_tokens(compact_json(tool_definition(tool)))


def _percentile(sorted_values: list[int], pct: float) -> int:
    if not sorted_values:
        return 0
    idx = max(0, min(len(sorted_values) - 1, math.ceil(pct * len(sorted_values)) - 1))
    return sorted_values[idx]


def catalog_stats(tools: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Per-tool and total token statistics for a tool list."""
    per_tool = {t["name"]: tool_tokens(t) for t in tools}
    values = sorted(per_tool.values())
    return {
        "estimator": estimator(),
        "tool_count": len(values),
        "total": sum(values),
        "median": int(statistics.median(values)) if values else 0,
        "p95": _percentile(values, 0.95),
        "max": values[-1] if values else 0,
        "heaviest": sorted(per_tool.items(), key=lambda kv: kv[1], reverse=True)[:5],
    }


def result_tokens(payload: Any) -> int:
    """Tokens of a tool call/result payload as the model would read it."""
    text = payload if isinstance(payload, str) else compact_json(payload)
    return count_tokens(text)
