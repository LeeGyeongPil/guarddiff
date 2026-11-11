"""Load and validate the prompt set (JSONL, one object per line)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .errors import ItemsError

LABELS = ("attack", "benign")


@dataclass(frozen=True)
class Item:
    id: str
    label: str  # "attack" | "benign"
    prompt: str
    lang: str | None = None
    category: str | None = None


def load_items(path: str | Path) -> list[Item]:
    """Read items from ``path``; raise ItemsError with a fix hint on any problem."""
    p = Path(path)
    if not p.is_file():
        raise ItemsError(f"items file not found: {p}. Set [run].items in your config to an existing .jsonl file.")
    items: list[Item] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        where = f"{p}:{lineno}"
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ItemsError(f"{where}: invalid JSON ({e.msg}). Each line must be one JSON object.") from e
        if not isinstance(obj, dict):
            raise ItemsError(f"{where}: expected a JSON object, got {type(obj).__name__}.")
        for key in ("id", "label", "prompt"):
            if not isinstance(obj.get(key), str) or not obj[key].strip():
                raise ItemsError(f"{where}: field '{key}' is required and must be a non-empty string.")
        if obj["label"] not in LABELS:
            raise ItemsError(f"{where}: label must be 'attack' or 'benign', got {obj['label']!r}.")
        if obj["id"] in seen:
            raise ItemsError(f"{where}: duplicate id {obj['id']!r}. Ids must be unique.")
        seen.add(obj["id"])
        items.append(Item(obj["id"], obj["label"], obj["prompt"], obj.get("lang"), obj.get("category")))
    if not items:
        raise ItemsError(f"no items found in {p}. Add at least one line like "
                         '{"id": "a1", "label": "attack", "prompt": "..."}.')
    return items
