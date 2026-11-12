"""Small user-style guard and target functions that the tests reference as "module:function"."""

from __future__ import annotations

import os

# Pin the output language before anything reads it. This is plain Python, not a pytest feature, so any test runner
# gets the same English messages even when LANG or LC_ALL is Korean.
os.environ["GUARDDIFF_LANG"] = "en"

import threading
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


# --- helpers for tests/test_concurrency.py (threads: everything shared is guarded by a lock) ---
GATE = {"barrier": None, "stop_prompt": None, "boom_prompt": None}  # tests set these, then reset them
_LOCK = threading.Lock()
_ACTIVE = {"now": 0, "max": 0}


def reset_gate() -> None:
    GATE.update(barrier=None, stop_prompt=None, boom_prompt=None)
    with _LOCK:
        _ACTIVE.update(now=0, max=0)


def max_active() -> int:
    with _LOCK:
        return _ACTIVE["max"]


def gate_target(prompt: str) -> str:
    """Counts how many calls are inside at once. With GATE['barrier'] set, every call waits there until all
    parties have arrived, so the barrier only opens when the calls really run at the same time."""
    with _LOCK:
        _ACTIVE["now"] += 1
        _ACTIVE["max"] = max(_ACTIVE["max"], _ACTIVE["now"])
    try:
        if GATE["stop_prompt"] == prompt:
            raise KeyboardInterrupt  # Ctrl-C inside a worker
        if GATE["boom_prompt"] == prompt:
            raise RuntimeError("target backend exploded")
        if GATE["barrier"] is not None:
            GATE["barrier"].wait()  # BrokenBarrierError (after its timeout) makes the pair indeterminate
        return _MOCK.call(prompt).text
    finally:
        with _LOCK:
            _ACTIVE["now"] -= 1
