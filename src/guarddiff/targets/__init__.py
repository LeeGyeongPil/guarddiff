"""Target adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors import ConfigError
from ..guards.python_fn import resolve_callable
from .base import Target, TargetReply, strip_thinking
from .mock import MockTarget
from .openai_http import OpenAIHTTPTarget
from .python_fn import PythonTarget

__all__ = ["Target", "TargetReply", "strip_thinking", "build_target"]

_ALLOWED = {
    "mock": {"self_refuse"},
    "python": {"callable"},
    "openai": {"model", "base_url", "max_tokens", "temperature", "api_key_env", "system", "timeout_s"},
}


def build_target(spec: dict[str, Any], base_dir: Path) -> Target:
    """Create the target from the ``[target]`` table (default: practice mock)."""
    ttype = spec.get("type", "mock")
    if ttype not in _ALLOWED:
        raise ConfigError(f"[target] unknown type {ttype!r}. Use one of: {', '.join(sorted(_ALLOWED))}.")
    unknown = set(spec) - {"type"} - _ALLOWED[ttype]
    if unknown:
        raise ConfigError(f"[target] unknown option(s) {sorted(unknown)} for type '{ttype}'.")
    if ttype == "mock":
        return MockTarget(spec.get("self_refuse"))
    if ttype == "python":
        ref = spec.get("callable")
        if not isinstance(ref, str):
            raise ConfigError("[target] type='python' needs callable = \"module:function\".")
        return PythonTarget(resolve_callable(ref, base_dir, "[target]"))
    kwargs = {k: v for k, v in spec.items() if k != "type"}
    return OpenAIHTTPTarget(**kwargs)
