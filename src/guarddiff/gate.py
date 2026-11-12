"""CI gate: compare one variant's metrics with limits."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ConfigError, GuarddiffError
from .i18n import t

# option name -> (metric key in summary, kind): "max" fails when value > limit, "min" when value < limit
LIMITS: dict[str, tuple[str, str]] = {
    "max_overblock": ("guard_overblock_rate", "max"),
    "min_asr_reduction": ("asr_reduction_vs_none", "min"),
    "max_p95_ms": ("guard_latency_ms_p95", "max"),
    "max_indeterminate": ("indeterminate_rate", "max"),
    "max_cost_usd": ("guard_cost_usd_total", "max"),
}


DEFAULT_MAX_INDETERMINATE = 0.0


@dataclass(frozen=True)
class GateFailure:
    metric: str
    value: float
    limit: float
    op: str  # ">" or "<"

    def __str__(self) -> str:
        return f"{self.metric} {self.value} {self.op} {self.limit}"


def load_summary(path: str | Path) -> dict[str, Any]:
    """Read a summary.json written by ``guarddiff run``."""
    p = Path(path)
    if not p.is_file():
        raise GuarddiffError(t("gate.summary_not_found", path=p))
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise GuarddiffError(t("gate.summary_bad_json", path=p, detail=e.msg)) from e
    if not isinstance(data, dict):
        raise GuarddiffError(t("gate.summary_not_object", path=p))
    return data


def check_gate(summary: dict[str, Any], variant: str, **limits: float | None) -> list[GateFailure]:
    """Return one GateFailure per limit that ``variant`` breaks (empty list = pass).

    ``summary`` is either the ``summary`` mapping (variant -> metrics) or the whole summary.json document.
    Unknown variants, unknown limit names and negative limits raise ConfigError.
    """
    per_variant = summary["summary"] if isinstance(summary.get("summary"), dict) else summary
    if variant not in per_variant:
        raise ConfigError(t("gate.unknown_variant", variant=variant, available=sorted(per_variant)))
    metrics = per_variant[variant]
    # A guard that failed on many items looks "good" (nothing was missed), so by default no failed items are
    # allowed. Pass max_indeterminate=<rate> to loosen it, or max_indeterminate=None to switch the check off.
    limits = {"max_indeterminate": DEFAULT_MAX_INDETERMINATE, **limits}
    failures: list[GateFailure] = []
    for name, limit in limits.items():
        if name not in LIMITS:
            raise ConfigError(t("gate.unknown_limit", name=name, allowed=", ".join(sorted(LIMITS))))
        if limit is None:
            continue
        if not isinstance(limit, (int, float)) or math.isnan(limit) or limit < 0:
            raise ConfigError(t("gate.bad_limit", name=name, value=limit))
        key, kind = LIMITS[name]
        value = metrics.get(key)
        if value is None:
            raise ConfigError(t("gate.no_metric", key=key, variant=variant))
        if kind == "max" and value > limit:
            failures.append(GateFailure(key, value, limit, ">"))
        elif kind == "min" and value < limit:
            failures.append(GateFailure(key, value, limit, "<"))
    return failures
