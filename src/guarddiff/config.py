"""TOML config loading and validation. Relative paths are resolved from the config's folder."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ConfigError
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
        raise ConfigError(f"config file not found: {p}. Create one with `guarddiff init` or pass the right path.")
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{p}: invalid TOML ({e}).") from e
    except UnicodeDecodeError as e:
        raise ConfigError(f"{p}: the file must be UTF-8 text ({e.reason}).") from e
    return parse_config(data, p.resolve().parent, str(p))


def parse_config(data: dict[str, Any], base_dir: Path, where: str = "config") -> Config:
    unknown = set(data) - _TOP_KEYS
    if unknown:
        raise ConfigError(f"{where}: unknown top-level key(s) {sorted(unknown)}. Allowed: {sorted(_TOP_KEYS)}.")
    run = data.get("run", {})
    if not isinstance(run, dict) or set(run) - _RUN_KEYS:
        raise ConfigError(f"{where}: [run] may only contain {sorted(_RUN_KEYS)}.")
    items = run.get("items")
    if not isinstance(items, str) or not items:
        raise ConfigError(f"{where}: [run].items is required, for example items = \"items.jsonl\".")
    latency = run.get("latency", "simulated")
    if latency not in MODES:
        raise ConfigError(f"{where}: [run].latency must be 'simulated' or 'measured', got {latency!r}.")

    guards = data.get("guards", [])
    if not isinstance(guards, list) or not all(isinstance(g, dict) for g in guards):
        raise ConfigError(f"{where}: guards must be written as [[guards]] tables.")
    names = [g.get("name") for g in guards]
    dupes = sorted({n for n in names if names.count(n) > 1 and n is not None})
    if dupes:
        raise ConfigError(f"{where}: duplicate guard name(s) {dupes}. Names must be unique.")

    raw_variants = data.get("variants", [])
    if not isinstance(raw_variants, list) or not raw_variants:
        raise ConfigError(f"{where}: add at least one [[variants]] table (name + guards list), "
                          'for example name = "none" and guards = [].')
    variants: list[Variant] = []
    for v in raw_variants:
        if not isinstance(v, dict) or not isinstance(v.get("name"), str) or not v["name"]:
            raise ConfigError(f"{where}: every [[variants]] entry needs a 'name'.")
        vg = v.get("guards", [])
        if not isinstance(vg, list) or not all(isinstance(x, str) for x in vg):
            raise ConfigError(f"{where}: variant '{v['name']}': guards must be a list of guard names.")
        missing = [x for x in vg if x not in names]
        if missing:
            raise ConfigError(f"{where}: variant '{v['name']}' uses unknown guard(s) {missing}. "
                              f"Defined guards: {sorted(n for n in names if n)}.")
        variants.append(Variant(v["name"], vg))
    vnames = [v.name for v in variants]
    if len(set(vnames)) != len(vnames):
        raise ConfigError(f"{where}: duplicate variant names in {vnames}.")
    baseline = run.get("baseline", "none" if "none" in vnames else vnames[0])
    if baseline not in vnames:
        raise ConfigError(f"{where}: [run].baseline {baseline!r} is not one of the variants {vnames}.")

    target = data.get("target", {"type": "mock"})
    judge = data.get("judge", {"type": "rules"})
    if not isinstance(target, dict) or not isinstance(judge, dict):
        raise ConfigError(f"{where}: [target] and [judge] must be tables.")
    if judge.get("type", "rules") != "rules":
        raise ConfigError(f"{where}: [judge].type {judge.get('type')!r} is not supported yet; use 'rules'.")
    return Config(base_dir=base_dir, items_path=base_dir / items, baseline=baseline, latency=latency,
                  target=target, judge=judge, guards=guards, variants=variants)
