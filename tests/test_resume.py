"""AC-7: an interrupted run continues where it stopped."""

from __future__ import annotations

import json

import gd_testhelpers
import pytest

from conftest import item, write_project
from guarddiff import run_ablation
from guarddiff.cli import main
from guarddiff.runner import load_run


def _config(offline_dir):
    cfg = offline_dir / "guarddiff.toml"
    text = cfg.read_text(encoding="utf-8")
    swapped = text.replace('type = "mock"            # practice mock, not a real LLM',
                           'type = "python"\ncallable = "gd_testhelpers:counting_target"')
    assert swapped != text
    cfg.write_text(swapped, encoding="utf-8")
    return cfg


def test_resume_skips_done_pairs(offline_dir, tmp_path):
    cfg = _config(offline_dir)
    out = tmp_path / "out"
    gd_testhelpers.CALLS.clear()
    full = run_ablation(cfg, out)
    full_calls = len(gd_testhelpers.CALLS)
    assert full_calls == sum(r.target_called for r in full.rows) and len(full.rows) == 54

    path = out / "results.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:20]) + "\n", encoding="utf-8")  # pretend the run stopped after 20 pairs

    gd_testhelpers.CALLS.clear()
    second = run_ablation(cfg, out)
    remaining_calls = sum(r.target_called for r in full.rows[20:])  # pairs 21..54 that passed their guards
    assert len(gd_testhelpers.CALLS) == remaining_calls < full_calls
    assert second.meta["skipped_pairs"] == 20
    assert second.summary == full.summary
    assert len(path.read_text(encoding="utf-8").splitlines()) == 54

    # a third run has nothing left to do
    gd_testhelpers.CALLS.clear()
    run_ablation(cfg, out)
    assert gd_testhelpers.CALLS == []

    # --fresh starts over
    gd_testhelpers.CALLS.clear()
    fresh = run_ablation(cfg, out, fresh=True)
    assert len(gd_testhelpers.CALLS) == full_calls and fresh.meta["skipped_pairs"] == 0


def test_half_written_last_line_is_dropped_and_rerun(offline_dir, tmp_path):
    cfg = _config(offline_dir)
    out = tmp_path / "out"
    full = run_ablation(cfg, out)
    path = out / "results.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:10]) + '\n{"id": "en-atk-0', encoding="utf-8")  # crash mid-write
    again = run_ablation(cfg, out)
    assert again.summary == full.summary and len(again.rows) == 54


def test_edited_prompt_is_rerun(offline_dir, tmp_path):
    cfg = offline_dir / "guarddiff.toml"
    out = tmp_path / "out"
    run_ablation(cfg, out)
    items = offline_dir / "items.jsonl"
    items.write_text(items.read_text(encoding="utf-8").replace("pipe bomb", "pipe b0mb", 1), encoding="utf-8")
    again = run_ablation(cfg, out)
    assert again.meta["skipped_pairs"] == 51  # the three variants of the edited item are recomputed


# ---- Q-3: changed settings are never answered from an older results file ----

def test_changed_guard_config_reruns_only_that_variant(offline_dir, tmp_path):
    cfg = offline_dir / "guarddiff.toml"
    out = tmp_path / "out"
    first = run_ablation(cfg, out)
    text = cfg.read_text(encoding="utf-8")
    assert 'name = "A-keyword"' in text
    import re
    # replace the keyword guard's patterns with one that never matches
    new = re.sub(r"(name = \"A-keyword\"[^\[]*?patterns\s*=\s*)\[[^\]]*\]", r'\1["zzzz-never"]', text, count=1, flags=re.S)
    assert new != text
    cfg.write_text(new, encoding="utf-8")
    again = run_ablation(cfg, out)
    assert again.meta["skipped_pairs"] == 36 and again.meta["config_changed_pairs"] == 18
    assert again.summary["A"]["asr"] != first.summary["A"]["asr"]
    assert again.summary["none"] == first.summary["none"] and again.summary["B"] == first.summary["B"]
    # unchanged config: everything resumes
    third = run_ablation(cfg, out)
    assert third.meta["skipped_pairs"] == 54 and third.meta["config_changed_pairs"] == 0


def test_changed_judge_or_latency_mode_reruns(offline_dir, tmp_path):
    cfg = offline_dir / "guarddiff.toml"
    out = tmp_path / "out"
    run_ablation(cfg, out)
    assert run_ablation(cfg, out, latency="measured").meta["skipped_pairs"] == 0
    text = cfg.read_text(encoding="utf-8")
    cfg.write_text(text.replace('type = "rules"', 'type = "rules"\npatterns = ["never-matches-anything"]', 1),
                   encoding="utf-8")
    assert run_ablation(cfg, out, latency="measured").meta["skipped_pairs"] == 0


# ---- Q-12: pairs that failed (indeterminate) are run again; only decided rows are reused ----

TWO_ITEMS = [item("a1", "attack", "do something bad"), item("b1", "benign", "how do I bake bread")]


def _flaky_project(folder, broken: str):
    """none vs G. ``broken`` says which side fails while gd_testhelpers.FLAKY[broken] is True."""
    target = "flaky_target" if broken == "target" else "counting_target"
    guard = "flaky_guard" if broken == "guard" else "never_blocks"
    toml = f"""
[run]
items = "items.jsonl"
[target]
type = "python"
callable = "gd_testhelpers:{target}"
[[guards]]
name = "g"
type = "python"
callable = "gd_testhelpers:{guard}"
[[variants]]
name = "none"
guards = []
[[variants]]
name = "G"
guards = ["g"]
"""
    return write_project(folder, items=TWO_ITEMS, toml=toml)


@pytest.mark.parametrize("broken", ["guard", "target"])
def test_indeterminate_pairs_are_retried_after_the_cause_is_fixed(tmp_path, monkeypatch, broken):
    cfg = _flaky_project(tmp_path / "p", broken)
    out = tmp_path / "o"
    monkeypatch.setitem(gd_testhelpers.FLAKY, broken, True)
    first = run_ablation(cfg, out)
    failed = {(r.id, r.variant) for r in first.rows if r.outcome == "indeterminate"}
    assert failed == ({("a1", "G"), ("b1", "G")} if broken == "guard" else {(r.id, r.variant) for r in first.rows})

    # the cause is fixed (server back up / code fixed) but the config file is unchanged
    monkeypatch.setitem(gd_testhelpers.FLAKY, broken, False)
    gd_testhelpers.CALLS.clear()
    second = run_ablation(cfg, out)
    assert second.meta["retried_indeterminate_pairs"] == len(failed)
    assert second.meta["skipped_pairs"] == 4 - len(failed)  # decided rows are still reused
    assert len(gd_testhelpers.CALLS) == len(failed)  # only the failed pairs reached the target again
    assert all(s["indeterminate_rate"] == 0.0 for s in second.summary.values())
    assert {r.outcome for r in second.rows} == {"missed", "passed"}

    gd_testhelpers.CALLS.clear()
    third = run_ablation(cfg, out)
    assert third.meta["retried_indeterminate_pairs"] == 0 and third.meta["skipped_pairs"] == 4
    assert gd_testhelpers.CALLS == []


def test_rerun_after_a_fix_turns_a_failed_gate_into_a_pass(tmp_path, monkeypatch, capsys):
    cfg = _flaky_project(tmp_path / "p", "guard")
    out = tmp_path / "o"
    summary = str(out / "summary.json")
    monkeypatch.setitem(gd_testhelpers.FLAKY, "guard", True)
    assert main(["run", str(cfg), "--out", str(out)]) == 0
    assert main(["gate", summary, "--variant", "G", "--min-asr-reduction", "0.0"]) == 1

    monkeypatch.setitem(gd_testhelpers.FLAKY, "guard", False)
    capsys.readouterr()
    assert main(["run", str(cfg), "--out", str(out)]) == 0  # the same command, no --fresh
    text = capsys.readouterr().out
    assert "retry 2 indeterminate pairs" in text and "resumed_from_file=2" in text
    assert main(["gate", summary, "--variant", "G", "--min-asr-reduction", "0.0"]) == 0

    capsys.readouterr()
    assert main(["run", str(cfg), "--out", str(out)]) == 0
    assert "indeterminate pairs" not in capsys.readouterr().out  # nothing left to retry


# ---- Q-13: --only updates the chosen variants and keeps every other variant's rows ----

def _rows_of(path, variant: str) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if json.loads(ln)["variant"] == variant]


def test_only_keeps_rows_of_the_other_variants(offline_dir, tmp_path):
    cfg = _config(offline_dir)
    out = tmp_path / "out"
    path = out / "results.jsonl"
    run_ablation(cfg, out)
    a_rows = _rows_of(path, "A")
    assert len(a_rows) == 18

    partial = run_ablation(cfg, out, only=["B"])
    assert partial.variants == ["none", "B"] and len(partial.rows) == 36
    assert partial.meta["kept_other_pairs"] == 18
    assert len(path.read_text(encoding="utf-8").splitlines()) == 54
    assert _rows_of(path, "A") == a_rows  # untouched, byte for byte

    # `report` shows what the last run compared (none and B), not the kept A rows
    assert load_run(out).variants == ["none", "B"] and len(load_run(out).rows) == 36

    # the next full run finds all 54 pairs and calls nothing
    gd_testhelpers.CALLS.clear()
    full = run_ablation(cfg, out)
    assert full.meta["skipped_pairs"] == 54 and gd_testhelpers.CALLS == []

    # --fresh with --only recomputes the chosen variants only
    again = run_ablation(cfg, out, only=["B"], fresh=True)
    assert again.meta["skipped_pairs"] == 0 and len(again.rows) == 36
    assert len(path.read_text(encoding="utf-8").splitlines()) == 54 and _rows_of(path, "A") == a_rows


def test_interrupted_only_run_keeps_the_other_variants(offline_dir, tmp_path, monkeypatch):
    cfg = _config(offline_dir)
    out = tmp_path / "out"
    path = out / "results.jsonl"
    run_ablation(cfg, out)
    a_rows, none_rows = _rows_of(path, "A"), _rows_of(path, "none")
    path.write_text("\n".join(a_rows + none_rows) + "\n", encoding="utf-8")  # B was never run

    gd_testhelpers.CALLS.clear()
    monkeypatch.setitem(gd_testhelpers.STOP, "after_calls", 2)
    with pytest.raises(KeyboardInterrupt):
        run_ablation(cfg, out, only=["B"])
    assert _rows_of(path, "A") == a_rows and _rows_of(path, "none") == none_rows
    assert 1 <= len(_rows_of(path, "B")) < 18  # the B pairs finished before Ctrl-C are on disk too


def test_only_says_which_results_it_kept(offline_dir, tmp_path, capsys):
    cfg, out = str(offline_dir / "guarddiff.toml"), str(tmp_path / "out")
    assert main(["run", cfg, "--out", out]) == 0
    capsys.readouterr()
    assert main(["run", cfg, "--out", out, "--only", "B"]) == 0
    text = capsys.readouterr().out
    assert "resumed_from_file=36" in text and "kept 18 pairs of variants not run this time: A" in text
