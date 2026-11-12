"""Shared test helpers. All tests run offline: no network, no keys, no model weights."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

os.environ["GUARDDIFF_LANG"] = "en"  # import time, not a fixture: every runner gets English messages

TESTS = Path(__file__).parent
FIXTURES = TESTS / "fixtures"
PKG_EXAMPLES = TESTS.parent / "src" / "guarddiff" / "examples"

if str(TESTS) not in sys.path:  # lets configs say callable = "gd_testhelpers:fn"
    sys.path.insert(0, str(TESTS))


@pytest.fixture
def offline_dir(tmp_path: Path) -> Path:
    """A writable copy of the packaged offline example (config + the 18 fixture prompts)."""
    dest = tmp_path / "offline"
    dest.mkdir()
    shutil.copyfile(PKG_EXAMPLES / "offline" / "guarddiff.toml", dest / "guarddiff.toml")
    shutil.copyfile(FIXTURES / "items.jsonl", dest / "items.jsonl")
    return dest


@pytest.fixture
def expected() -> dict:
    return json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))


def write_project(folder: Path, *, items: list[dict], toml: str) -> Path:
    """Write items.jsonl and guarddiff.toml into ``folder`` and return the config path."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "items.jsonl").write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items),
                                        encoding="utf-8")
    cfg = folder / "guarddiff.toml"
    cfg.write_text(toml, encoding="utf-8")
    return cfg


def item(id_: str, label: str, prompt: str) -> dict:
    return {"id": id_, "label": label, "prompt": prompt}
