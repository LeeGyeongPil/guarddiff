"""Latency helpers: deterministic simulated values for reproducible demos."""

from __future__ import annotations

import hashlib

MODES = ("simulated", "measured")


def simulated_latency(item_id: str, guard_name: str, base_ms: float) -> float:
    """base * (1 + jitter), jitter in [0, 1) derived from sha256 of 'item:guard'.

    The same item and guard always give the same value, so reports are reproducible.
    """
    h = int(hashlib.sha256(f"{item_id}:{guard_name}".encode()).hexdigest()[:8], 16)
    return round(base_ms * (1.0 + (h % 1000) / 1000.0), 3)
