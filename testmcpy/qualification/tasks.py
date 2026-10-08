"""Task suite loader."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Step:
    tool: str
    args: dict[str, Any]
    workspace: str | None = None
    discovery: str | None = None
    expect_error: str | None = None
    expect_denied: bool = False
    answer_excludes: list[str] = field(default_factory=list)


@dataclass
class Task:
    id: str
    title: str
    topology: str
    principal: str
    workspace: str | None
    steps: list[Step]
    oracle: dict[str, Any]
    surface_expect: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def writes_expected(self) -> bool:
        return bool(self.oracle.get("ledger"))


def load_tasks(path: str | Path) -> list[Task]:
    data = yaml.safe_load(Path(path).read_text())
    tasks = []
    for raw in data["tasks"]:
        steps = [
            Step(
                tool=s["tool"],
                args=s.get("args") or {},
                workspace=s.get("workspace"),
                discovery=s.get("discovery"),
                expect_error=s.get("expect_error"),
                expect_denied=bool(s.get("expect_denied")),
                answer_excludes=list(s.get("answer_excludes") or []),
            )
            for s in raw["steps"]
        ]
        tasks.append(
            Task(
                id=raw["id"],
                title=raw["title"],
                topology=raw["topology"],
                principal=raw["principal"],
                workspace=raw.get("workspace"),
                steps=steps,
                oracle=raw.get("oracle") or {},
                surface_expect=raw.get("surface_expect") or {},
            )
        )
    return tasks
