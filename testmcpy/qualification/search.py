"""Tool search used where no recorded real search response applies.

``rank_tools`` is a small, dependency-free BM25 over tool name, description and
top-level parameter names. It stands in for a producer's or provider's search
index on the synthetic scale catalog and for permission-filtered principals.
It is NOT the Superset implementation: the actual catalog's generic surface
replays the real ``search_tools`` responses recorded from Superset's own
transform, and the report says which ranker produced each number.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

_WORD = re.compile(r"[a-z0-9]+")
MAX_DESCRIPTION_CHARS = 300  # Superset MCP_TOOL_SEARCH_CONFIG["max_description_length"]


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower().replace("_", " "))


def _doc(tool: dict[str, Any]) -> list[str]:
    props = list(((tool.get("inputSchema") or {}).get("properties") or {}).keys())
    return (
        _tokens(tool["name"]) * 2
        + _tokens(tool.get("description", "") or "")
        + _tokens(" ".join(props))
    )


def rank_tools(
    tools: list[dict[str, Any]], query: str, limit: int = 5, k1: float = 1.5, b: float = 0.75
) -> list[dict[str, Any]]:
    """Return the top ``limit`` tools for ``query`` (stable on ties, by catalog order)."""
    q = _tokens(query)
    if not q or not tools:
        return list(tools[:limit])
    exact = [t for t in tools if t["name"] == query.strip()]
    docs = [_doc(t) for t in tools]
    n = len(docs)
    avgdl = sum(len(d) for d in docs) / n or 1.0
    df: Counter[str] = Counter()
    for d in docs:
        df.update(set(d))
    scored: list[tuple[float, int]] = []
    for idx, d in enumerate(docs):
        tf = Counter(d)
        score = 0.0
        for term in q:
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(d) / avgdl))
        scored.append((score, idx))
    scored.sort(key=lambda s: (-s[0], s[1]))
    ranked = [tools[i] for score, i in scored if score > 0]
    ordered = exact + [t for t in ranked if t not in exact]
    return ordered[:limit]


def search_result_entry(tool: dict[str, Any]) -> dict[str, Any]:
    """A search hit shaped like Superset's serializer output (definition, truncated prose)."""
    desc = (tool.get("description") or "")[:MAX_DESCRIPTION_CHARS]
    entry: dict[str, Any] = {
        "name": tool["name"],
        "title": (tool.get("annotations") or {}).get("title"),
        "description": desc,
        "inputSchema": tool.get("inputSchema"),
        "annotations": tool.get("annotations"),
    }
    return {k: v for k, v in entry.items() if v is not None}
