"""Shared benchmark helpers.

A benchmark runs one suite across the cross product of models × providers ×
MCP profiles × repeats — single runs are statistical noise, so the
``/performance`` matrix needs the same suite executed repeatedly under multiple
configs. The combo expansion lives here so the ``testmcpy bench`` CLI and the
websocket benchmark runner build the exact same matrix.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkCombo:
    """One (model, provider, profile, iteration) point in the matrix.

    ``provider``/``profile`` are ``None`` when unset (falls back to the run
    command's defaults). ``iteration`` is 1-based.
    """

    model: str
    provider: str | None
    profile: str | None
    iteration: int


class BenchmarkComboError(ValueError):
    """Raised when the inputs can't form a valid matrix (e.g. the providers
    list can't be aligned to the models list)."""


def _as_list(value: str | Sequence[str] | None) -> list[str]:
    """Accept either a comma-separated string (CLI) or an already-split
    list (websocket JSON) and return a clean list of non-empty items."""
    if value is None:
        return []
    items: Iterable[str]
    items = value.split(",") if isinstance(value, str) else value
    return [item.strip() for item in items if item and str(item).strip()]


def build_benchmark_combos(
    models: str | Sequence[str] | None,
    providers: str | Sequence[str] | None = None,
    profiles: str | Sequence[str] | None = None,
    repeat: int = 1,
) -> list[BenchmarkCombo]:
    """Expand the benchmark matrix.

    ``providers`` aligns to ``models`` (a single value broadcasts to all; a
    mismatched length is an error). ``profiles`` is a full product dimension
    (defaults to a single ``None`` = the default profile). Order is
    model → profile → iteration, matching the original CLI.
    """
    if repeat < 1:
        raise BenchmarkComboError("repeat must be >= 1")

    model_list = _as_list(models)
    if not model_list:
        raise BenchmarkComboError("at least one model is required")

    profile_raw = _as_list(profiles)
    profile_list: list[str | None] = list(profile_raw) if profile_raw else [None]

    provider_raw = _as_list(providers)
    provider_list: list[str | None]
    if provider_raw:
        provider_list = list(provider_raw)
        if len(provider_list) == 1:
            provider_list = provider_list * len(model_list)
        if len(provider_list) != len(model_list):
            raise BenchmarkComboError(
                f"{len(provider_list)} providers for {len(model_list)} models — "
                "pass one per model or a single value"
            )
    else:
        provider_list = [None] * len(model_list)

    return [
        BenchmarkCombo(model=model, provider=provider, profile=profile, iteration=iteration)
        for model, provider in zip(model_list, provider_list, strict=True)
        for profile in profile_list
        for iteration in range(1, repeat + 1)
    ]


def combo_label(combo: BenchmarkCombo) -> str:
    """Human-readable config label, e.g. ``assistant/claude-sonnet-4-6 @ prod``."""
    label = f"{combo.provider or 'default'}/{combo.model}"
    if combo.profile:
        label += f" @ {combo.profile}"
    return label
