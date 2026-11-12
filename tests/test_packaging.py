"""AC-10: no runtime dependencies in the core; a missing extra ends with an install hint."""

from __future__ import annotations

import gd_testhelpers  # noqa: F401  (importing it pins GUARDDIFF_LANG=en for this test file)

import tomllib
from pathlib import Path

import pytest

from conftest import item, write_project
from guarddiff import MissingExtraError, run_ablation
from guarddiff.cli import main
from guarddiff.guards import qwen3guard

ROOT = Path(__file__).parent.parent
TOML = """
[run]
items = "items.jsonl"
[[guards]]
name = "live"
type = "hf-qwen3guard"
mode = "loose"
[[variants]]
name = "none"
guards = []
[[variants]]
name = "live"
guards = ["live"]
"""


def test_core_has_no_runtime_deps_and_hf_hint(tmp_path, monkeypatch, capsys):
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert meta["project"]["dependencies"] == []
    assert {"transformers>=4.51", "torch", "accelerate"} <= set(meta["project"]["optional-dependencies"]["hf"])
    assert meta["project"]["scripts"]["guarddiff"] == "guarddiff.cli:main"
    assert meta["project"]["license"] == "MIT"

    monkeypatch.setattr(qwen3guard, "_module_available", lambda name: False)  # pretend the extra is absent
    cfg = write_project(tmp_path / "p", items=[item("a", "attack", "x")], toml=TOML)
    with pytest.raises(MissingExtraError) as exc:
        run_ablation(cfg, tmp_path / "o")
    assert "uv sync --extra hf" in str(exc.value) and 'pip install "guarddiff[hf]"' in str(exc.value)

    assert main(["run", str(cfg), "--out", str(tmp_path / "o2")]) == 2
    err = capsys.readouterr().err
    assert "uv sync --extra hf" in err and 'pip install "guarddiff[hf]"' in err


def test_variants_that_do_not_use_the_guard_still_run_without_the_extra(tmp_path, monkeypatch):
    monkeypatch.setattr(qwen3guard, "_module_available", lambda name: False)
    cfg = write_project(tmp_path / "p", items=[item("a", "attack", "x")], toml=TOML)
    result = run_ablation(cfg, tmp_path / "o", only=["none"])
    assert result.variants == ["none"]


def test_packaged_examples_and_license_files_exist():
    pkg = ROOT / "src" / "guarddiff"
    for rel in ("examples/offline/guarddiff.toml", "examples/offline/items.jsonl",
                "examples/qwen3guard-recorded/guarddiff.toml", "packs/starter-en-ko.jsonl", "packs/LICENSE"):
        assert (pkg / rel).is_file(), rel
    assert (ROOT / "LICENSE").is_file() and (ROOT / "CHANGELOG.md").is_file()
