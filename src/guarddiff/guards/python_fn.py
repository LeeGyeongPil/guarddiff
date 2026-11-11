"""User-supplied guard: ``fn(text) -> bool | (bool, reason)`` referenced as "module:function"."""

from __future__ import annotations

import importlib
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from ..errors import ConfigError
from .base import Guard, GuardVerdict


class GuardTimeout(TimeoutError):
    """The guard function did not answer within ``timeout_s``."""


def resolve_callable(ref: str, base_dir: Path | None, what: str) -> Callable[..., Any]:
    """Import "module:function"; the config's folder is searched while importing."""
    mod_name, sep, fn_name = ref.partition(":")
    if not sep or not mod_name or not fn_name:
        raise ConfigError(f"{what}: callable must look like 'module:function', got {ref!r}.")
    added = False
    if base_dir is not None and str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))
        added = True
    try:
        module = importlib.import_module(mod_name)
    except ImportError as e:
        raise ConfigError(f"{what}: cannot import module '{mod_name}' ({e}). "
                          "Put it next to the config file or install it.") from e
    finally:
        if added:
            sys.path.remove(str(base_dir))
    fn = getattr(module, fn_name, None)
    if not callable(fn):
        raise ConfigError(f"{what}: '{mod_name}' has no callable named '{fn_name}'.")
    return fn


class PythonGuard(Guard):
    def __init__(self, name: str, fn: Callable[[str], Any], stage: str = "input", *,
                 timeout_s: float | None = None, **kwargs: Any) -> None:
        super().__init__(name, stage, **kwargs)
        self._fn = fn
        self._timeout_s = timeout_s

    def _call(self, text: str) -> Any:
        if self._timeout_s is None:
            return self._fn(text)
        # One daemon thread per call: a stuck call cannot delay the next item, and a daemon thread
        # never keeps the interpreter from exiting (a pooled worker would be joined at exit).
        box: dict[str, Any] = {}

        def work() -> None:
            try:
                box["value"] = self._fn(text)
            except BaseException as e:  # noqa: BLE001 - re-raised in the caller's thread
                box["error"] = e

        thread = threading.Thread(target=work, name="guarddiff-guard", daemon=True)
        thread.start()
        thread.join(self._timeout_s)
        if thread.is_alive():
            raise GuardTimeout(f"no answer within {self._timeout_s}s")
        if "error" in box:
            raise box["error"]
        return box["value"]

    def check(self, text: str, *, item_id: str, prompt: str) -> GuardVerdict:
        result = self._call(text)
        if isinstance(result, bool):
            return GuardVerdict(result, "guard function returned True" if result else None)
        if (isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], bool)
                and (result[1] is None or isinstance(result[1], str))):
            return GuardVerdict(result[0], result[1] or "guard function returned True" if result[0] else None)
        raise TypeError("guard function must return bool or (bool, reason: str | None), "
                        f"got {type(result).__name__}")
