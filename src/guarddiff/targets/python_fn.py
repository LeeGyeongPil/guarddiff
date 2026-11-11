"""User-supplied target: ``fn(prompt: str) -> str`` referenced as "module:function"."""

from __future__ import annotations

from typing import Any, Callable

from .base import Target, TargetReply, strip_thinking


class PythonTarget(Target):
    def __init__(self, fn: Callable[[str], Any]) -> None:
        self._fn = fn

    def call(self, prompt: str) -> TargetReply:
        result = self._fn(prompt)
        if not isinstance(result, str):
            raise TypeError(f"target function must return str, got {type(result).__name__}")
        return TargetReply(strip_thinking(result))  # reasoning text is not part of the answer
