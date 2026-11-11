"""Regex guard: block when any pattern matches (case-insensitive)."""

from __future__ import annotations

import re
from typing import Any

from ..errors import ConfigError
from .base import Guard, GuardVerdict


class RegexGuard(Guard):
    def __init__(self, name: str, patterns: list[str], stage: str = "input", **kwargs: Any) -> None:
        super().__init__(name, stage, **kwargs)
        if not patterns:
            raise ConfigError(f"guard '{name}': 'patterns' must be a non-empty list of regular expressions.")
        self._compiled: list[re.Pattern[str]] = []
        for p in patterns:
            try:
                self._compiled.append(re.compile(p, re.IGNORECASE))
            except (re.error, TypeError) as e:
                raise ConfigError(f"guard '{name}': invalid regex {p!r} ({e}).") from e

    def check(self, text: str, *, item_id: str, prompt: str) -> GuardVerdict:
        for c in self._compiled:
            m = c.search(text)
            if m:
                return GuardVerdict(True, f"regex '{c.pattern}' matched '{m.group(0)}'")
        return GuardVerdict(False)
