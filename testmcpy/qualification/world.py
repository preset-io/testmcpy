"""Deterministic fixture world: workspaces, principals, roles, data and a write ledger.

Everything the qualification suite touches lives in memory. Write tools mutate
only ``World.data`` and are recorded in ``World.ledger`` so oracles can assert
exactly what was (and was not) written. Nothing here talks to a network or a
real Superset.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any

ROLE_PERMS: dict[str, frozenset[str]] = {
    "admin": frozenset({"read", "write", "sql", "admin"}),
    "alpha": frozenset({"read", "write", "sql"}),
    "gamma": frozenset({"read"}),
}
SQL_TOOLS = frozenset({"execute_sql", "save_sql_query", "open_sql_lab_with_context"})

KNOWLEDGE_TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_knowledge",
        "description": "Search the workspace Knowledge base (documents and glossary). "
        "Fixture-only tool: the real Knowledge contract is not defined yet.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "request": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search text"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                }
            },
            "required": ["request"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
            "title": "Search knowledge",
        },
        "_meta": {"synthetic": True, "fixture_extra": "knowledge"},
    },
    {
        "name": "get_knowledge_document",
        "description": "Fetch one Knowledge document by id. Fixture-only tool.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "request": {
                    "type": "object",
                    "properties": {"document_id": {"type": "string"}},
                    "required": ["document_id"],
                }
            },
            "required": ["request"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
            "title": "Get knowledge document",
        },
        "_meta": {"synthetic": True, "fixture_extra": "knowledge"},
    },
]


class FixtureError(Exception):
    """A platform-level (out-of-band) failure with a stable typed code."""

    def __init__(self, code: str, message: str, **data: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def payload(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, **self.data}}


@dataclass
class Workspace:
    id: str
    name: str
    producer: str  # "current" (named tools) | "legacy" (generic compatibility only)
    knowledge_enabled: bool
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Principal:
    name: str
    role: str
    grants: dict[str, str]  # workspace id -> "active" | "revoked"

    @property
    def permissions(self) -> frozenset[str]:
        return ROLE_PERMS[self.role]


def required_permission(tool: dict[str, Any]) -> str:
    """Permission class a tool needs: ``sql``, ``write`` or ``read``."""
    if tool["name"].split("__", 1)[0] in SQL_TOOLS:
        return "sql"
    if (tool.get("annotations") or {}).get("readOnlyHint"):
        return "read"
    return "write"


def tool_allowed(principal: Principal, tool: dict[str, Any]) -> bool:
    return required_permission(tool) in principal.permissions


def _seed_acme() -> dict[str, Any]:
    return {
        "databases": [{"id": 1, "database_name": "examples", "backend": "sqlite"}],
        "datasets": [
            {
                "id": 10,
                "table_name": "sales",
                "database_id": 1,
                "columns": ["region", "revenue", "order_date"],
            },
            {"id": 11, "table_name": "customers", "database_id": 1, "columns": ["id", "name"]},
        ],
        "charts": [
            {"id": 100, "slice_name": "Revenue by Region", "viz_type": "echarts_timeseries_bar"},
            {"id": 101, "slice_name": "Monthly Orders", "viz_type": "echarts_timeseries_line"},
        ],
        "dashboards": [
            {"id": 200, "dashboard_title": "Sales Overview", "chart_ids": [100, 101]},
            {"id": 201, "dashboard_title": "Customer Health", "chart_ids": []},
        ],
        "sql": {
            "select region, sum(revenue) as revenue from sales group by region": {
                "columns": ["region", "revenue"],
                "rows": [["EMEA", 1200], ["AMER", 3400], ["APAC", 900]],
            },
            "select count(*) as n from customers": {"columns": ["n"], "rows": [[42]]},
        },
        "knowledge": [
            {
                "id": "kb-1",
                "title": "Revenue definition",
                "text": "Revenue is recognised on shipment.",
            }
        ],
    }


def _seed_beta() -> dict[str, Any]:
    return {
        "databases": [{"id": 7, "database_name": "retail_dw", "backend": "postgresql"}],
        "datasets": [
            {"id": 70, "table_name": "stores", "database_id": 7, "columns": ["store", "visits"]}
        ],
        "charts": [{"id": 300, "slice_name": "Store Footfall", "viz_type": "table"}],
        "dashboards": [{"id": 400, "dashboard_title": "Retail Pulse", "chart_ids": [300]}],
        "sql": {},
        "knowledge": [],
    }


def default_workspaces() -> dict[str, Workspace]:
    return {
        "ws-a": Workspace("ws-a", "Acme Analytics", "current", True, _seed_acme()),
        "ws-b": Workspace("ws-b", "Beta Retail", "current", False, _seed_beta()),
        "ws-old": Workspace("ws-old", "Legacy Co", "legacy", False, _seed_acme()),
    }


def default_principals() -> dict[str, Principal]:
    return {
        "alice": Principal(
            "alice", "admin", {"ws-a": "active", "ws-b": "active", "ws-old": "active"}
        ),
        "bob": Principal("bob", "gamma", {"ws-a": "active"}),
        "carol": Principal("carol", "alpha", {"ws-a": "active", "ws-b": "revoked"}),
        "dave": Principal("dave", "alpha", {"ws-a": "active"}),
    }


def _norm_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().rstrip(";")).lower()


def _page(
    items: list[dict[str, Any]], req: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    page = int(req.get("page") or 1)
    size = int(req.get("page_size") or 10)
    start = (page - 1) * size
    sel = items[start : start + size]
    return sel, {
        "count": len(sel),
        "total_count": len(items),
        "page": page,
        "page_size": size,
        "has_next": start + size < len(items),
    }


def _search(items: list[dict[str, Any]], req: dict[str, Any], key: str) -> list[dict[str, Any]]:
    term = (req.get("search") or "").lower()
    out = [i for i in items if term in str(i.get(key, "")).lower()] if term else list(items)
    for f in req.get("filters") or []:
        if f.get("col") == key and f.get("opr") in {"eq", "ilike", "ct", "like"}:
            needle = str(f.get("value", "")).strip("%").lower()
            out = [i for i in out if needle in str(i.get(key, "")).lower()]
    return out


class World:
    """Mutable fixture state plus the handlers that implement the named tools."""

    def __init__(self) -> None:
        self.workspaces = default_workspaces()
        self.principals = default_principals()
        self.ledger: list[dict[str, Any]] = []
        self._next_id = 5000

    def snapshot_data(self) -> dict[str, Any]:
        return copy.deepcopy({k: w.data for k, w in self.workspaces.items()})

    # -- helpers ---------------------------------------------------------
    def workspace_for(self, principal: Principal, workspace_id: str) -> Workspace:
        ws = self.workspaces.get(workspace_id)
        if ws is None:
            raise FixtureError("UNKNOWN_WORKSPACE", f"Workspace '{workspace_id}' does not exist")
        status = principal.grants.get(workspace_id)
        if status is None:
            raise FixtureError(
                "ACCESS_DENIED",
                f"No grant for workspace '{workspace_id}'",
                workspace_id=workspace_id,
            )
        if status == "revoked":
            raise FixtureError(
                "ACCESS_REVOKED",
                f"Your access to workspace '{workspace_id}' was revoked; ask a workspace admin.",
                workspace_id=workspace_id,
            )
        return ws

    def extra_tools(self, ws: Workspace) -> list[dict[str, Any]]:
        return copy.deepcopy(KNOWLEDGE_TOOLS) if ws.knowledge_enabled else []

    # -- tool execution --------------------------------------------------
    def execute(
        self,
        principal: Principal,
        ws: Workspace,
        tool: dict[str, Any],
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """Run one named tool. Raises ``FixtureError`` for platform-level failures."""
        name = tool["name"].split("__", 1)[0]  # synthetic scale clones act like their source
        if not tool_allowed(principal, tool):
            raise FixtureError(
                "PERMISSION_DENIED",
                f"Role '{principal.role}' cannot use '{tool['name']}' "
                f"(needs {required_permission(tool)}).",
                tool=tool["name"],
            )
        if (tool.get("_meta") or {}).get("fixture_extra") == "knowledge" and not (
            ws.knowledge_enabled
        ):
            raise FixtureError(
                "FEATURE_DISABLED",
                "Knowledge is disabled for this workspace.",
                feature="knowledge",
            )
        req = args.get("request") if isinstance(args.get("request"), dict) else {}
        handler = getattr(self, f"_h_{name}", None)
        if handler is None:
            if required_permission(tool) != "read":
                self.ledger.append(
                    {"op": name, "workspace": ws.id, "by": principal.name, "stub": True}
                )
            return {"fixture_stub": True, "tool": name}
        result: dict[str, Any] = handler(principal, ws, req)
        return result

    # -- handlers (shapes follow the real tools, trimmed) ----------------
    def _h_health_check(self, p: Principal, ws: Workspace, req: dict[str, Any]) -> dict[str, Any]:
        return {"status": "healthy", "workspace": ws.id}

    def _h_get_instance_info(
        self, p: Principal, ws: Workspace, req: dict[str, Any]
    ) -> dict[str, Any]:
        d = ws.data
        return {
            "instance_summary": {
                "total_dashboards": len(d["dashboards"]),
                "total_charts": len(d["charts"]),
                "total_datasets": len(d["datasets"]),
                "total_databases": len(d["databases"]),
            },
            "current_user": {"username": p.name, "roles": [p.role]},
            "feature_availability": {"knowledge": ws.knowledge_enabled},
        }

    def _h_list_charts(self, p: Principal, ws: Workspace, req: dict[str, Any]) -> dict[str, Any]:
        items = _search(ws.data["charts"], req, "slice_name")
        sel, meta = _page(items, req)
        return {**meta, "charts": sel}

    def _h_get_chart_info(self, p: Principal, ws: Workspace, req: dict[str, Any]) -> dict[str, Any]:
        ident = req.get("identifier")
        for c in ws.data["charts"]:
            if c["id"] == ident or str(c["id"]) == str(ident):
                return dict(c)
        return {"error_type": "not_found", "message": f"ChartInfo '{ident}' not found"}

    def _h_list_datasets(self, p: Principal, ws: Workspace, req: dict[str, Any]) -> dict[str, Any]:
        items = _search(ws.data["datasets"], req, "table_name")
        sel, meta = _page(items, req)
        return {**meta, "datasets": sel}

    def _h_get_dataset_info(
        self, p: Principal, ws: Workspace, req: dict[str, Any]
    ) -> dict[str, Any]:
        ident = req.get("identifier")
        for d in ws.data["datasets"]:
            if d["id"] == ident or str(d["id"]) == str(ident) or d["table_name"] == ident:
                return dict(d)
        return {"error_type": "not_found", "message": f"Dataset '{ident}' not found"}

    def _h_list_dashboards(
        self, p: Principal, ws: Workspace, req: dict[str, Any]
    ) -> dict[str, Any]:
        items = _search(ws.data["dashboards"], req, "dashboard_title")
        sel, meta = _page(items, req)
        return {**meta, "dashboards": sel}

    def _h_get_dashboard_info(
        self, p: Principal, ws: Workspace, req: dict[str, Any]
    ) -> dict[str, Any]:
        ident = req.get("identifier")
        for d in ws.data["dashboards"]:
            if d["id"] == ident or str(d["id"]) == str(ident):
                return dict(d)
        return {"error_type": "not_found", "message": f"Dashboard '{ident}' not found"}

    def _h_list_databases(self, p: Principal, ws: Workspace, req: dict[str, Any]) -> dict[str, Any]:
        items = _search(ws.data["databases"], req, "database_name")
        sel, meta = _page(items, req)
        return {**meta, "databases": sel}

    def _h_execute_sql(self, p: Principal, ws: Workspace, req: dict[str, Any]) -> dict[str, Any]:
        db_ids = {d["id"] for d in ws.data["databases"]}
        if req.get("database_id") not in db_ids:
            return {
                "success": False,
                "error_type": "DATABASE_NOT_FOUND_ERROR",
                "error": f"Database with ID {req.get('database_id')} not found.",
            }
        sql = _norm_sql(str(req.get("sql", "")))
        if not sql.startswith(("select", "with")):
            return {
                "success": False,
                "error_type": "READ_ONLY_DATABASE",
                "error": "Fixture databases are read-only.",
            }
        canned = ws.data["sql"].get(sql)
        if canned is None:
            return {"success": True, "columns": [], "rows": [], "row_count": 0}
        return {
            "success": True,
            "columns": canned["columns"],
            "rows": canned["rows"],
            "row_count": len(canned["rows"]),
        }

    def _h_get_chart_type_schema(
        self, p: Principal, ws: Workspace, req: dict[str, Any]
    ) -> dict[str, Any]:
        return {"chart_type": req.get("chart_type"), "fixture_stub": True}

    def _h_generate_chart(self, p: Principal, ws: Workspace, req: dict[str, Any]) -> dict[str, Any]:
        dataset = next(
            (
                d
                for d in ws.data["datasets"]
                if d["id"] == req.get("dataset_id") or str(d["id"]) == str(req.get("dataset_id"))
            ),
            None,
        )
        if dataset is None:
            return {
                "chart": None,
                "error": {"error_type": "CHART_DATASET_NOT_FOUND", "message": "Dataset not found"},
            }
        if not req.get("save_chart"):
            return {"chart": None, "preview_only": True, "dataset_id": dataset["id"]}
        self._next_id += 1
        chart = {
            "id": self._next_id,
            "slice_name": req.get("chart_name") or "Untitled chart",
            "viz_type": (req.get("config") or {}).get("chart_type", "table"),
            "datasource_id": dataset["id"],
        }
        ws.data["charts"].append(chart)
        self.ledger.append(
            {"op": "create_chart", "workspace": ws.id, "by": p.name, "id": chart["id"]}
        )
        return {"chart": chart, "saved": True}

    def _h_search_knowledge(
        self, p: Principal, ws: Workspace, req: dict[str, Any]
    ) -> dict[str, Any]:
        term = str(req.get("query", "")).lower()
        hits = [k for k in ws.data["knowledge"] if term in (k["title"] + k["text"]).lower()]
        return {"results": hits}

    def _h_get_knowledge_document(
        self, p: Principal, ws: Workspace, req: dict[str, Any]
    ) -> dict[str, Any]:
        for k in ws.data["knowledge"]:
            if k["id"] == req.get("document_id"):
                return dict(k)
        return {"error_type": "not_found"}
