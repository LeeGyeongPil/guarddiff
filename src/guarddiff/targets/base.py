"""Target protocol: the model (or app) the guards protect."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_THINK_CLOSED = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN = re.compile(r"<think>.*\Z", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks (and an unterminated trailing one) from reasoning models."""
    return _THINK_OPEN.sub("", _THINK_CLOSED.sub("", text)).strip()


@dataclass
class TargetReply:
    text: str
    usage: dict[str, int] = field(default_factory=dict)  # prompt_tokens / completion_tokens when known
    error: str | None = None  # set when the call failed (HTTP error, timeout, exception)


class Target:
    """Base class. ``call`` should not raise for expected failures; set ``error`` instead."""

    def call(self, prompt: str) -> TargetReply:
        raise NotImplementedError

    def close(self) -> None:
        """Release connections (default: nothing)."""
