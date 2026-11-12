"""Load and validate the prompt set (JSONL, one object per line)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .errors import ItemsError
from .i18n import t

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
        raise ItemsError(t("items.not_found", path=p))
    items: list[Item] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        where = f"{p}:{lineno}"
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ItemsError(t("items.bad_json", where=where, detail=e.msg)) from e
        if not isinstance(obj, dict):
            raise ItemsError(t("items.not_object", where=where, type=type(obj).__name__))
        for key in ("id", "label", "prompt"):
            if not isinstance(obj.get(key), str) or not obj[key].strip():
                raise ItemsError(t("items.field", where=where, key=key))
        if obj["label"] not in LABELS:
            raise ItemsError(t("items.label", where=where, value=obj["label"]))
        if obj["id"] in seen:
            raise ItemsError(t("items.dup_id", where=where, value=obj["id"]))
        seen.add(obj["id"])
        items.append(Item(obj["id"], obj["label"], obj["prompt"], obj.get("lang"), obj.get("category")))
    if not items:
        raise ItemsError(t("items.empty", path=p, example='{"id": "a1", "label": "attack", "prompt": "..."}'))
    return items
