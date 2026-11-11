"""Guard protocol. A guard looks at text and says block / pass."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GuardVerdict:
    blocked: bool
    reason: str | None = None
    latency_ms: float | None = None  # set when the latency is known (replayed recording)
    cost_usd: float | None = None  # None -> the guard's unit_cost_usd


class Guard:
    """Base class. Subclasses implement :meth:`check`; raising means "indeterminate"."""

    def __init__(self, name: str, stage: str = "input", *, unit_cost_usd: float = 0.0,
                 sim_latency_ms: float | None = None) -> None:
        self.name = name
        self.stage = stage  # "input" checks the prompt, "output" checks the model answer
        self.unit_cost_usd = unit_cost_usd
        self.sim_latency_ms = sim_latency_ms  # base for simulated latency; None -> measure

    def prepare(self) -> None:
        """Load heavy resources before the first check (default: nothing)."""

    def check(self, text: str, *, item_id: str, prompt: str) -> GuardVerdict:
        raise NotImplementedError

    def close(self) -> None:
        """Release threads, models, connections (default: nothing)."""
