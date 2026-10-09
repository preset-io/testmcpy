"""Sanitise raw client output and build clients/summary.json.

Raw stream-json (Claude Code) / --json (Codex) files are read from --raw-dir. The
repo copy drops model reasoning, local paths and socket names, and caps any single
tool-result text at 6000 characters (marked), so the traces stay reviewable. The
summary extracts exactly what the matrix cites: tool registration, tool calls and
their status, permission denials, token usage and the final answer.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

CAP = 6000
DROP_INIT = {"memory_paths", "messaging_socket_path", "session_id", "cwd", "uuid"}

# file stem -> run description
MANIFEST: dict[str, dict[str, Any]] = {}


def _add(stem: str, client: str, surface: str, catalog: str, task: str, **kw: Any) -> None:
    MANIFEST[stem] = {"client": client, "surface": surface, "catalog": catalog, "task": task, **kw}


for s, surf, cat in (("generic", "generic", "actual"), ("native", "native_eager", "actual"),
                     ("scale", "native_eager", "scale")):
    _add(f"cc-t1-{s}", "claude-code", surf, cat, "trivial", tool_search_env=None, allowed=False)
for s, surf, cat in (("generic", "generic", "actual"), ("native", "native_eager", "actual"),
                     ("scale", "native_eager", "scale")):
    _add(f"cc-t4-{s}-auto-trivial", "claude-code", surf, cat, "trivial", tool_search_env="auto",
         allowed=False)
for s in ("generic", "native"):
    for allow in ("noallow", "allow"):
        _add(f"cc-t2-{s}-{allow}", "claude-code", "generic" if s == "generic" else "native_eager",
             "actual", "chart-find", tool_search_env=None, allowed=allow == "allow")
_add("cc-t3-scale-ts-true", "claude-code", "native_eager", "scale", "chart-find",
     tool_search_env="true", allowed=True)
_add("cc-t3-scale-ts-auto", "claude-code", "native_eager", "scale", "chart-find",
     tool_search_env="auto", allowed=True)
_add("cc-t4-native-auto-task", "claude-code", "native_eager", "actual", "chart-find",
     tool_search_env="auto", allowed=True)
_add("cc-t5-ws-generic", "claude-code", "generic", "actual", "workspace-switch",
     tool_search_env=None, allowed=True, topology="gateway")
_add("cc-t5-ws-native", "claude-code", "native_eager", "actual", "workspace-switch",
     tool_search_env=None, allowed=True, topology="gateway")
_add("cc-t6-bob-generic", "claude-code", "generic", "actual", "restricted-role",
     tool_search_env=None, allowed=True)
_add("cc-t6-bob-native", "claude-code", "native_eager", "actual", "restricted-role",
     tool_search_env=None, allowed=True)
_add("cc-t7-kd-generic", "claude-code", "generic", "actual", "knowledge-disabled",
     tool_search_env=None, allowed=True)
_add("cc-t7-kd-native", "claude-code", "native_eager", "actual", "knowledge-disabled",
     tool_search_env=None, allowed=True)
for s, surf, cat in (("generic", "generic", "actual"), ("native", "native_eager", "actual"),
                     ("scale", "native_eager", "scale")):
    _add(f"cx-t1-{s}", "codex", surf, cat, "trivial", approved=False)
    _add(f"cx-t2-{s}", "codex", surf, cat, "chart-find", approved=False)
_add("cx-t3-generic-approve", "codex", "generic", "actual", "chart-find", approved=True)
for s, surf, cat in (("generic", "generic", "actual"), ("native", "native_eager", "actual"),
                     ("scale", "native_eager", "scale")):
    for i in (1, 2, 3):
        _add(f"cx-n-{s}-{i}", "codex", surf, cat, "chart-find", approved=True, trial=i)

ORACLE = {
    "chart-find": ("Revenue by Region",),
    "workspace-switch": ("Store Footfall", "Revenue by Region"),
}


def _clean_text(s: str) -> str:
    s = re.sub(r"/home/[A-Za-z0-9_.-]+", "<home>", s)
    if len(s) > CAP:
        s = s[:CAP] + f"...[truncated {len(s) - CAP} chars]"
    return s


def _clean(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, str):
        return _clean_text(obj)
    return obj


def sanitise_claude(lines: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kept, info = [], {"tools": [], "calls": [], "denials": [], "answer": "", "usage": {}}
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        t, st = e.get("type"), e.get("subtype")
        if t == "system" and st == "init":
            info.update(
                client_version=e["claude_code_version"], model=e["model"],
                api_key_source=e["apiKeySource"], permission_mode=e["permissionMode"],
                mcp_servers=e["mcp_servers"], tools_registered=len(e["tools"]),
                mcp_tools_registered=sum(1 for x in e["tools"] if x.startswith("mcp__")),
                tool_search_builtin_present="ToolSearch" in e["tools"],
            )
            e = {k: v for k, v in e.items() if k not in DROP_INIT}
            e["tools"] = [x for x in e["tools"] if not x.startswith("mcp__")] + [
                f"<{info['mcp_tools_registered']} mcp__fixture__* tools>"
            ]
            kept.append(_clean(e))
        elif t == "assistant":
            for c in e["message"]["content"]:
                if c.get("type") == "tool_use":
                    info["calls"].append(c["name"])
            msg = dict(e["message"])
            msg["content"] = [c for c in msg["content"] if c.get("type") != "thinking"]
            kept.append(_clean({"type": "assistant", "message": msg}))
        elif t == "user":
            kept.append(_clean(e))
        elif t == "result":
            info["usage"] = e.get("usage", {})
            info["turns"] = e.get("num_turns")
            info["denials"] = [d["tool_name"] for d in e.get("permission_denials", [])]
            info["answer"] = e.get("result", "")
            kept.append(_clean({k: e[k] for k in ("type", "subtype", "is_error", "num_turns",
                                                   "duration_ms", "result", "usage",
                                                   "permission_denials") if k in e}))
    u = info["usage"]
    info["prompt_tokens_total"] = sum(
        u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens",
                                  "cache_read_input_tokens"))
    return kept, info


def sanitise_codex(lines: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kept, info = [], {"calls": [], "call_status": [], "answer": "", "usage": {}}
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e["type"] == "item.completed":
            it = e["item"]
            if it["type"] == "reasoning":
                continue
            if it["type"] == "mcp_tool_call":
                info["calls"].append(f"{it['server']}.{it['tool']}")
                info["call_status"].append(it["status"])
                if it.get("error"):
                    info.setdefault("errors", []).append(it["error"].get("message"))
            if it["type"] == "agent_message":
                info["answer"] = it["text"]
        if e["type"] == "turn.completed":
            info["usage"] = e["usage"]
        kept.append(_clean(e))
    info["prompt_tokens_total"] = info["usage"].get("input_tokens")
    return kept, info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--claude-version", required=True)
    ap.add_argument("--codex-version", required=True)
    args = ap.parse_args()
    raw, out = Path(args.raw_dir), Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    runs = []
    for stem, meta in sorted(MANIFEST.items()):
        path = raw / f"{stem}.jsonl"
        if not path.exists():
            continue
        lines = path.read_text().splitlines()
        if meta["client"] == "claude-code":
            kept, info = sanitise_claude(lines)
        else:
            kept, info = sanitise_codex(lines)
        needles = ORACLE.get(meta["task"])
        info["answer_correct"] = (
            all(n in info["answer"] for n in needles) if needles else None
        )
        (out / f"{stem}.jsonl").write_text(
            "\n".join(json.dumps(k, sort_keys=True, separators=(",", ":")) for k in kept) + "\n"
        )
        runs.append({"run": stem, **meta, **{k: v for k, v in info.items() if k != "usage"},
                     "usage": info["usage"]})
    summary = {
        "claude_code_version": args.claude_version,
        "codex_version": args.codex_version,
        "runs": runs,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(f"{len(runs)} runs summarised")


if __name__ == "__main__":
    main()
