"""Replay guard: answers from a recorded JSONL instead of running the guard model.

Each line: {"id", "raw" or "guard_label", "categories", "latency_ms"}. A missing id is an
error (counted as indeterminate), never a pass.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..errors import ConfigError, GuardParseError
from .base import Guard, GuardVerdict
from .qwen3guard import BLOCK_LABELS, LABELS, blocks, parse_output, reason_for


class ReplayGuard(Guard):
    def __init__(self, name: str, path: Path, stage: str = "input", *, mode: str | None = None,
                 block_labels: list[str] | None = None, **kwargs: Any) -> None:
        super().__init__(name, stage, **kwargs)
        if block_labels is None and mode is None:
            raise ConfigError(f"guard '{name}': set mode = \"strict\" | \"loose\" or block_labels = [...].")
        if mode is not None and mode not in BLOCK_LABELS:
            raise ConfigError(f"guard '{name}': mode must be 'strict' or 'loose', got {mode!r}.")
        self._mode = mode
        self._block_labels = set(block_labels) if block_labels is not None else None
        self._records = self._load(Path(path))

    @staticmethod
    def _load(path: Path) -> dict[str, dict[str, Any]]:
        if not path.is_file():
            raise ConfigError(f"replay file not found: {path}. Set 'path' to a recorded .jsonl file.")
        records: dict[str, dict[str, Any]] = {}
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
                records[str(rec["id"])] = rec
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                raise ConfigError(f"{path}:{lineno}: invalid replay record ({type(e).__name__}). "
                                  'Each line needs at least {"id": ..., "raw": ...}.') from e
        return records

    def check(self, text: str, *, item_id: str, prompt: str) -> GuardVerdict:
        rec = self._records.get(item_id)
        if rec is None:
            raise LookupError(f"no recorded guard answer for id {item_id!r}")
        if rec.get("raw"):
            out = parse_output(rec["raw"])
            label, reason = out.label, reason_for(out)
        elif rec.get("guard_label") in LABELS:
            label = rec["guard_label"]
            reason = f"label {label}, categories {', '.join(rec.get('categories') or ['-'])}"
        else:
            raise GuardParseError(f"recorded answer for {item_id!r} has no parsable label")
        if self._block_labels is not None:
            blocked = label in self._block_labels
        else:
            blocked = blocks(label, self._mode or "")
        latency = rec.get("latency_ms")
        return GuardVerdict(blocked, reason if blocked else None,
                            latency_ms=float(latency) if latency is not None else None)
