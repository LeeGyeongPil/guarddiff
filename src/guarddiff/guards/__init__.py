"""Guard adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors import ConfigError
from .base import Guard, GuardVerdict
from .python_fn import PythonGuard, resolve_callable
from .qwen3guard import HFQwen3Guard
from .regex import RegexGuard
from .replay import ReplayGuard

__all__ = ["Guard", "GuardVerdict", "build_guard"]

_COMMON = {"name", "type", "stage", "unit_cost_usd", "sim_latency_ms"}
_ALLOWED = {
    "regex": {"patterns"},
    "python": {"callable", "timeout_s"},
    "replay": {"path", "mode", "block_labels"},
    "hf-qwen3guard": {"mode", "model", "max_new_tokens"},
}


def build_guard(spec: dict[str, Any], base_dir: Path) -> Guard:
    """Create a guard from one ``[[guards]]`` table."""
    name = spec.get("name")
    if not isinstance(name, str) or not name:
        raise ConfigError("every [[guards]] entry needs a non-empty 'name'.")
    gtype = spec.get("type")
    if gtype not in _ALLOWED:
        raise ConfigError(f"guard '{name}': unknown type {gtype!r}. Use one of: {', '.join(sorted(_ALLOWED))}.")
    stage = spec.get("stage", "input")
    if stage == "tool":
        raise ConfigError("tool stage is planned for a later release")
    if stage not in ("input", "output"):
        raise ConfigError(f"guard '{name}': stage must be 'input' or 'output', got {stage!r}.")
    unknown = set(spec) - _COMMON - _ALLOWED[gtype]
    if unknown:
        raise ConfigError(f"guard '{name}': unknown option(s) {sorted(unknown)} for type '{gtype}'.")
    common: dict[str, Any] = {"unit_cost_usd": float(spec.get("unit_cost_usd", 0.0))}
    if spec.get("sim_latency_ms") is not None:
        common["sim_latency_ms"] = float(spec["sim_latency_ms"])
    if gtype == "regex":
        return RegexGuard(name, spec.get("patterns") or [], stage, **common)
    if gtype == "python":
        ref = spec.get("callable")
        if not isinstance(ref, str):
            raise ConfigError(f"guard '{name}': 'callable' = \"module:function\" is required.")
        return PythonGuard(name, resolve_callable(ref, base_dir, f"guard '{name}'"), stage,
                           timeout_s=spec.get("timeout_s"), **common)
    if gtype == "replay":
        if not isinstance(spec.get("path"), str):
            raise ConfigError(f"guard '{name}': 'path' to the recorded .jsonl is required.")
        return ReplayGuard(name, base_dir / spec["path"], stage, mode=spec.get("mode"),
                           block_labels=spec.get("block_labels"), **common)
    kwargs = {k: spec[k] for k in ("model", "max_new_tokens") if k in spec}
    return HFQwen3Guard(name, stage, mode=spec.get("mode", "strict"), **kwargs, **common)
