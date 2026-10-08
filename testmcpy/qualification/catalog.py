"""Catalog fixtures: a captured real tools/list and a deterministic scale catalog."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The domains used to derive synthetic tools. Fixed order => deterministic output.
_SCALE_DOMAINS = (
    "finance",
    "ops",
    "hr",
    "marketing",
    "support",
    "supply",
    "risk",
    "legal",
    "product",
    "growth",
)


@dataclass
class Catalog:
    """A named set of tool definitions for each surface family."""

    name: str
    native_tools: list[dict[str, Any]]
    generic_tools: list[dict[str, Any]]
    search_responses: dict[str, Any] = field(default_factory=dict)
    initialize: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    output_schemas: dict[str, Any] = field(default_factory=dict)
    synthetic_count: int = 0

    def recorded_hits(self, query: str | None) -> list[dict[str, Any]] | None:
        """Real ``search_tools`` hits recorded for ``query`` (actual catalog only)."""
        recorded = self.search_responses.get(query or "")
        if recorded is None or self.synthetic_count:
            return None
        hits: list[dict[str, Any]] = json.loads(recorded["content"][0]["text"])
        return hits

    def native_by_name(self) -> dict[str, dict[str, Any]]:
        return {t["name"]: t for t in self.native_tools}


def load_catalog(
    path: str | Path,
    output_schemas_path: str | Path | None = None,
    search_responses_path: str | Path | None = None,
) -> Catalog:
    """Load a catalog captured by ``capture/capture_superset_catalog.py``.

    The capture is split into three files so each stays reviewable: the tool
    definitions, the (large, rarely forwarded) output schemas, and the real
    ``search_tools`` responses recorded for the task suite's queries.
    """
    data = json.loads(Path(path).read_text())
    pages = data["native"]["pages"]
    tools = [t for page in pages for t in page]
    outputs: dict[str, Any] = {}
    if output_schemas_path and Path(output_schemas_path).exists():
        outputs = json.loads(Path(output_schemas_path).read_text())["output_schemas"]
    searches: dict[str, Any] = {}
    if search_responses_path and Path(search_responses_path).exists():
        searches = json.loads(Path(search_responses_path).read_text())["search_responses"]
    return Catalog(
        name="actual",
        native_tools=tools,
        generic_tools=data["generic"]["tools"],
        search_responses=searches,
        initialize=data.get("initialize", {}),
        provenance=data.get("provenance", {}),
        output_schemas=outputs,
    )


def scale_catalog(base: Catalog, target: int = 150) -> Catalog:
    """Extend ``base`` to ``target`` native tools with derived synthetic tools.

    Each synthetic tool clones a real tool's description and schema (so schema
    weight is realistic) under a domain-suffixed name, e.g.
    ``list_charts__finance``. Real tools are never altered, and the
    clones are flagged in ``_meta`` so reports can separate real from derived.
    A catalog already at or above ``target`` is returned unchanged.
    """
    real = [copy.deepcopy(t) for t in base.native_tools]
    if len(real) >= target:
        return Catalog(
            name="scale",
            native_tools=real,
            generic_tools=copy.deepcopy(base.generic_tools),
            search_responses=copy.deepcopy(base.search_responses),
            initialize=copy.deepcopy(base.initialize),
            provenance={**base.provenance, "scale_target": target, "synthetic_added": 0},
        )
    seen = {t["name"] for t in real}
    synthetic: list[dict[str, Any]] = []
    i = 0
    while len(real) + len(synthetic) < target:
        src = base.native_tools[i % len(base.native_tools)]
        domain = _SCALE_DOMAINS[(i // len(base.native_tools) + i) % len(_SCALE_DOMAINS)]
        name = f"{src['name']}__{domain}"
        i += 1
        if name in seen:
            continue
        seen.add(name)
        clone = copy.deepcopy(src)
        clone["name"] = name
        clone["_meta"] = {
            **(clone.get("_meta") or {}),
            "synthetic": True,
            "derived_from": src["name"],
        }
        synthetic.append(clone)
    return Catalog(
        name="scale",
        native_tools=real + synthetic,
        generic_tools=copy.deepcopy(base.generic_tools),
        search_responses=copy.deepcopy(base.search_responses),
        initialize=copy.deepcopy(base.initialize),
        provenance={
            **base.provenance,
            "scale_target": target,
            "synthetic_added": len(synthetic),
            "synthetic_rule": "clone real tool schema/description under <name>__<domain>",
        },
        synthetic_count=len(synthetic),
    )
