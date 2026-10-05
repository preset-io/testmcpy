"""Shared normalization of tool-call trace entries for the evaluators.

A recorded tool call can take several shapes, and every evaluator that asks
"which tool ran, and with what arguments?" must read them the same way:

* **Direct** -- ``{"name": "list_dashboards", "arguments": {...}}``
* **Prefixed** -- ``{"name": "mcp__ns__list_dashboards", ...}``
* **Gateway (current)** -- ``call_tool`` with
  ``{"workspace_id": "123", "tool_name": "list_dashboards", "args": {...}}``
* **Gateway (legacy)** -- ``call_tool`` with
  ``{"name"|"tool_name": "list_dashboards", "arguments": {...}}``
* **Discovery** -- ``search_tools`` / ``search_workspace_tools``. These look a
  tool up; they never execute it, so ``kind`` is ``"discovery"`` and they are
  not tool executions for the purpose of any "was it called" assertion.

``normalize_tool_call`` turns any of these into a ``NormalizedToolCall`` that
keeps the gateway routing identity (``workspace_id``) next to the tool's own
arguments, so two workspaces calling the same tool stay distinguishable.

Known limits (deliberately not handled here):

* Only ``search_tools`` and ``search_workspace_tools`` are treated as discovery;
  other gateway meta-tools (``list_workspaces`` etc.) remain ordinary calls.
* Arguments are never merged across calls; a retry is a separate entry.

Deferred compatibility gaps (existing behavior, intentionally left alone):

* ``UnnecessaryToolCalls`` still reads raw trace entries. With
  ``check_args=True`` workspace identity is part of the signature (it lives in
  the arguments), but ``check_args=False`` groups every gateway call under
  ``call_tool``.
* ``scoring.real_tool_name`` (false-positive rate) keeps its own, narrower
  name extraction and ignores the workspace.
* Loose name matching (substring, e.g. ``list_charts`` also matching
  ``list_charts_v2``) and ``partial_match``'s "expected value under any key"
  fallback in ``tool_called_with_parameters`` are unchanged.
* ``execution_successful`` / ``no_tool_call_errors`` inspect tool *results*, not
  call shapes, and are unaffected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from testmcpy.scoring import real_tool_name

# Gateway tools that discover tools without executing them.
DISCOVERY_TOOLS = frozenset({"search_tools", "search_workspace_tools"})
# The gateway tool that executes another tool by name.
GATEWAY_TOOL = "call_tool"

KIND_EXECUTION = "execution"
KIND_DISCOVERY = "discovery"
KIND_MALFORMED = "malformed_gateway"


@dataclass(frozen=True)
class NormalizedToolCall:
    """One trace entry in canonical form.

    ``name`` is the tool that ran: the prefix-stripped inner tool for a gateway
    call, otherwise the prefix-stripped call name. ``raw_name`` is the name as
    recorded and ``gateway`` the outer gateway tool (``None`` for direct calls).
    ``arguments`` are the tool's own arguments, without the gateway envelope.
    """

    kind: str
    name: str
    raw_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    gateway: str | None = None
    workspace_id: str | None = None
    # False when a gateway envelope's arguments were present but unusable
    # (not an object, or an unparseable JSON string).
    arguments_valid: bool = True
    # The arguments exactly as recorded on the call (the gateway envelope for a
    # gateway call), for assertions that target the gateway tool itself.
    envelope_arguments: dict[str, Any] = field(default_factory=dict, compare=False)
    raw: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def is_execution(self) -> bool:
        return self.kind == KIND_EXECUTION

    @property
    def is_discovery(self) -> bool:
        return self.kind == KIND_DISCOVERY

    @property
    def effective_arguments(self) -> dict[str, Any]:
        """Arguments with a ``request`` wrapper flattened (see ``flatten_request``)."""
        return flatten_request(self.arguments)

    def as_dict(self) -> dict[str, Any]:
        """JSON-friendly form for eval ``details``."""
        out: dict[str, Any] = {
            "kind": self.kind,
            "name": self.name,
            "raw_name": self.raw_name,
            "arguments": self.arguments,
        }
        if self.gateway:
            out["gateway"] = self.gateway
        if self.workspace_id is not None:
            out["workspace_id"] = self.workspace_id
        if not self.arguments_valid:
            out["arguments_valid"] = False
        return out


def flatten_request(arguments: dict[str, Any]) -> dict[str, Any]:
    """Unwrap the ``{"request": {...}}`` envelope some tool schemas use.

    A sole ``request`` object is replaced by its contents; a ``request`` next
    to other keys is merged into them (request keys win).
    """
    request = arguments.get("request")
    if not isinstance(request, dict):
        return arguments
    if len(arguments) == 1:
        return request
    flat = {k: v for k, v in arguments.items() if k != "request"}
    flat.update(request)
    return flat


def _as_arguments(value: Any) -> tuple[dict[str, Any], bool]:
    """Coerce a recorded arguments value to ``(dict, valid)``.

    ``None``/missing is a valid empty set; a JSON-object string is parsed;
    anything else is invalid and yields ``{}``.
    """
    if value is None:
        return {}, True
    if isinstance(value, dict):
        return value, True
    if isinstance(value, str):
        try:
            parsed = json.loads(value) if value.strip() else {}
        except (ValueError, TypeError):
            return {}, False
        if isinstance(parsed, dict):
            return parsed, True
    return {}, False


def normalize_tool_call(call: dict[str, Any]) -> NormalizedToolCall:
    """Normalize one trace entry. Never raises on malformed input."""
    if not isinstance(call, dict):
        return NormalizedToolCall(KIND_MALFORMED, "", "", arguments_valid=False)

    raw_name = str(call.get("name") or call.get("tool_name") or "")
    canonical = real_tool_name({"name": raw_name}) if raw_name else ""
    arguments, args_ok = _as_arguments(call.get("arguments"))

    if canonical in DISCOVERY_TOOLS:
        return NormalizedToolCall(
            KIND_DISCOVERY,
            canonical,
            raw_name,
            arguments,
            arguments_valid=args_ok,
            envelope_arguments=arguments,
            raw=call,
        )

    if canonical != GATEWAY_TOOL:
        return NormalizedToolCall(
            KIND_EXECUTION,
            canonical,
            raw_name,
            arguments,
            arguments_valid=args_ok,
            envelope_arguments=arguments,
            raw=call,
        )

    # Gateway dispatch: tool identity and routing live in the envelope.
    inner = arguments.get("name") or arguments.get("tool_name")
    workspace_id = arguments.get("workspace_id")
    workspace = str(workspace_id) if workspace_id is not None else None
    if not isinstance(inner, str) or not inner or not args_ok:
        # No usable target (or an unreadable envelope): not an execution of any
        # named tool. It stays visible as the gateway call it was.
        return NormalizedToolCall(
            KIND_MALFORMED,
            canonical,
            raw_name,
            {},
            gateway=raw_name,
            workspace_id=workspace,
            arguments_valid=False,
            envelope_arguments=arguments,
            raw=call,
        )

    # Current shape uses ``args``; the legacy shape uses ``arguments``.
    inner_key = "args" if "args" in arguments else "arguments"
    inner_args, inner_ok = _as_arguments(arguments.get(inner_key))
    return NormalizedToolCall(
        KIND_EXECUTION,
        real_tool_name({"name": inner}),
        inner,
        inner_args,
        gateway=raw_name,
        workspace_id=workspace,
        arguments_valid=inner_ok,
        envelope_arguments=arguments,
        raw=call,
    )


def normalize_tool_calls(tool_calls: list[dict[str, Any]] | None) -> list[NormalizedToolCall]:
    """Normalize a whole trace, preserving order."""
    return [normalize_tool_call(c) for c in tool_calls or []]
