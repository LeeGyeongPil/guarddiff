"""Exception hierarchy. The CLI maps every GuarddiffError to exit code 2."""

from __future__ import annotations


class GuarddiffError(Exception):
    """Base class for all errors guarddiff raises on purpose."""


class ConfigError(GuarddiffError):
    """The TOML config (or a command-line option) is invalid."""


class ItemsError(GuarddiffError):
    """The items JSONL file is missing or malformed."""


class MissingExtraError(GuarddiffError):
    """An optional dependency group is not installed."""


class GuardParseError(GuarddiffError):
    """A guard model answered in a format we cannot parse."""
