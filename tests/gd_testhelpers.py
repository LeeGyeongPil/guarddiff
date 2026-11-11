"""Small user-style guard and target functions that the tests reference as "module:function"."""

from __future__ import annotations

import time

from guarddiff.targets.mock import MockTarget

CALLS: list[str] = []  # prompts the counting target has seen
STOP = {"after_calls": None}  # counting_target acts like Ctrl-C once it has answered this many prompts
FLAKY = {"guard": False, "target": False}  # True = that flaky_* function fails (a server that is down)
_MOCK = MockTarget()


def raising_guard(text: str) -> bool:
    raise RuntimeError("guard backend exploded")


def flaky_guard(text: str) -> bool:
    """Fails while FLAKY['guard'] is set; never blocks once it is "fixed" (the config file stays the same)."""
    if FLAKY["guard"]:
        raise ConnectionError("guard server is down")
    return False


def flaky_target(prompt: str) -> str:
    """Returns an empty answer while FLAKY['target'] is set, the mock answer otherwise."""
    CALLS.append(prompt)
    return "" if FLAKY["target"] else _MOCK.call(prompt).text


def slow_guard(text: str) -> bool:
    time.sleep(0.4)
    return False


def never_blocks(text: str) -> bool:
    return False


def counting_target(prompt: str) -> str:
    if STOP["after_calls"] is not None and len(CALLS) >= STOP["after_calls"]:
        raise KeyboardInterrupt  # the user pressed Ctrl-C in the middle of a run
    CALLS.append(prompt)
    return _MOCK.call(prompt).text


def empty_target(prompt: str) -> str:
    return ""


def thinking_only_target(prompt: str) -> str:
    return "<think>I should answer, but I am still thinking"


def first_item_slow_guard(text: str) -> bool:
    """Hangs for a while only on the prompt 'x'; every other prompt is answered at once."""
    if text == "x":
        time.sleep(3)
    return False


def hanging_guard(text: str) -> bool:
    """Sleeps far longer than any test timeout (a stuck backend)."""
    time.sleep(20)
    return False


def blocks_everything(text: str) -> bool:
    return True
