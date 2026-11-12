"""TOML config loading and validation. Relative paths are resolved from the config's folder."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ConfigError
from .i18n import t
from .latency import MODES

_TOP_KEYS = {"run", "target", "judge", "guards", "variants"}
_RUN_KEYS = {"items", "baseline", "latency"}


@dataclass
class Variant:
    name: str
    guards: list[str]


@dataclass
class Config:
    base_dir: Path
    items_path: Path
    baseline: str
    latency: str
    target: dict[str, Any]
    judge: dict[str, Any]
    guards: list[dict[str, Any]]
    variants: list[Variant] = field(default_factory=list)


def load_config(path: str | Path) -> Config:
    """Read and validate a guarddiff TOML file. Raises ConfigError with a fix hint."""
    p = Path(path)
    if not p.is_file():
        raise ConfigError(t("config.not_found", path=p))
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(t("config.bad_toml", path=p, detail=e)) from e
    except UnicodeDecodeError as e:
        raise ConfigError(t("config.not_utf8", path=p, detail=e.reason)) from e
    return parse_config(data, p.resolve().parent, str(p))


def parse_config(data: dict[str, Any], base_dir: Path, where: str = "config") -> Config:
    unknown = set(data) - _TOP_KEYS
    if unknown:
        raise ConfigError(t("config.unknown_top", where=where, unknown=sorted(unknown), allowed=sorted(_TOP_KEYS)))
    run = data.get("run", {})
    if not isinstance(run, dict) or set(run) - _RUN_KEYS:
        raise ConfigError(t("config.run_keys", where=where, allowed=sorted(_RUN_KEYS)))
    items = run.get("items")
    if not isinstance(items, str) or not items:
        raise ConfigError(t("config.items_required", where=where))
    latency = run.get("latency", "simulated")
    if latency not in MODES:
        raise ConfigError(t("config.latency", where=where, value=latency))

    guards = data.get("guards", [])
    if not isinstance(guards, list) or not all(isinstance(g, dict) for g in guards):
        raise ConfigError(t("config.guards_tables", where=where))
    names = [g.get("name") for g in guards]
    dupes = sorted({n for n in names if names.count(n) > 1 and n is not None})
    if dupes:
        raise ConfigError(t("config.dup_guards", where=where, names=dupes))

    raw_variants = data.get("variants", [])
    if not isinstance(raw_variants, list) or not raw_variants:
        raise ConfigError(t("config.no_variants", where=where))
    variants: list[Variant] = []
    for v in raw_variants:
        if not isinstance(v, dict) or not isinstance(v.get("name"), str) or not v["name"]:
            raise ConfigError(t("config.variant_name", where=where))
        vg = v.get("guards", [])
        if not isinstance(vg, list) or not all(isinstance(x, str) for x in vg):
            raise ConfigError(t("config.variant_guards", where=where, variant=v["name"]))
        missing = [x for x in vg if x not in names]
        if missing:
            raise ConfigError(t("config.variant_unknown_guard", where=where, variant=v["name"], missing=missing,
                                defined=sorted(n for n in names if n)))
        variants.append(Variant(v["name"], vg))
    vnames = [v.name for v in variants]
    if len(set(vnames)) != len(vnames):
        raise ConfigError(t("config.dup_variants", where=where, names=vnames))
    baseline = run.get("baseline", "none" if "none" in vnames else vnames[0])
    if baseline not in vnames:
        raise ConfigError(t("config.baseline", where=where, value=baseline, names=vnames))

    target = data.get("target", {"type": "mock"})
    judge = data.get("judge", {"type": "rules"})
    if not isinstance(target, dict) or not isinstance(judge, dict):
        raise ConfigError(t("config.tables", where=where))
    if judge.get("type", "rules") != "rules":
        raise ConfigError(t("config.judge_type", where=where, value=judge.get("type")))
    return Config(base_dir=base_dir, items_path=base_dir / items, baseline=baseline, latency=latency,
                  target=target, judge=judge, guards=guards, variants=variants)
