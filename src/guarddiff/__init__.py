"""guarddiff: run the same prompts with guardrails off and on, and compare what changes."""

from __future__ import annotations

from .config import Config, load_config
from .errors import ConfigError, GuarddiffError, ItemsError, MissingExtraError
from .gate import GateFailure, check_gate
from .outcomes import ResultRow
from .runner import RunResult, run_ablation

__version__ = "0.3.0"

__all__ = [
    "Config", "ConfigError", "GateFailure", "GuarddiffError", "ItemsError", "MissingExtraError",
    "ResultRow", "RunResult", "check_gate", "load_config", "run_ablation", "__version__",
]
