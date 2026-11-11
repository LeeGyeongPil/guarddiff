"""``run --concurrency N``: real parallel calls, deterministic results, failures stay local."""

from __future__ import annotations

import json
import threading

import gd_testhelpers
import pytest

from conftest import item, write_project
from guarddiff import run_ablation
from guarddiff.cli import main
from guarddiff.errors import ConfigError

ITEMS = [item(f"i{n}", "attack" if n % 2 else "benign", f"question number {n}") for n in range(6)]

TOML = """\
[run]
items = "items.jsonl"
baseline = "none"
latency = "simulated"
[target]
type = "python"
callable = "gd_testhelpers:gate_target"
[judge]
type = "rules"
[[guards]]
name = "slowish"
type = "python"
callable = "gd_testhelpers:never_blocks"
sim_latency_ms = 5.0
[[variants]]
name = "none"
guards = []
[[variants]]
name = "G"
guards = ["slowish"]
"""


@pytest.fixture(autouse=True)
def _clean_gate():
    gd_testhelpers.reset_gate()
    yield
    gd_testhelpers.reset_gate()


def _cfg(folder, items=ITEMS):
    return write_project(folder, items=items, toml=TOML)


def _files(out):
    return ((out / "results.jsonl").read_bytes(), (out / "summary.json").read_bytes())


def test_barrier_proves_real_parallel_calls(tmp_path):
    # 4 calls must be inside the target together for the barrier to open; run serially it breaks
    gd_testhelpers.GATE["barrier"] = threading.Barrier(4, timeout=5)
    cfg = _cfg(tmp_path / "p", ITEMS[:4])
    result = run_ablation(cfg, tmp_path / "o", only=["none"], concurrency=4)
    assert {r.outcome for r in result.rows} <= {"passed", "model_refused", "missed", "blocked"}
    assert "indeterminate" not in {r.outcome for r in result.rows}
    assert gd_testhelpers.max_active() == 4


def test_barrier_breaks_when_not_parallel(tmp_path):
    # the barrier test above is meaningful: with concurrency=1 the same barrier cannot open
    gd_testhelpers.GATE["barrier"] = threading.Barrier(2, timeout=0.2)
    cfg = _cfg(tmp_path / "p", ITEMS[:2])
    result = run_ablation(cfg, tmp_path / "o", only=["none"])
    assert {r.outcome for r in result.rows} == {"indeterminate"}


def test_default_is_sequential(tmp_path):
    run_ablation(_cfg(tmp_path / "p"), tmp_path / "o")
    assert gd_testhelpers.max_active() == 1


def test_final_files_do_not_depend_on_concurrency(tmp_path):
    cfg = _cfg(tmp_path / "p")
    run_ablation(cfg, tmp_path / "one")
    run_ablation(cfg, tmp_path / "four", concurrency=4)
    run_ablation(cfg, tmp_path / "big", concurrency=100)  # more workers than pairs is fine
    assert _files(tmp_path / "one") == _files(tmp_path / "four") == _files(tmp_path / "big")
    lines = (tmp_path / "four" / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 12 and '"id": "i0"' in lines[0] and '"id": "i5"' in lines[-1]


def test_one_failing_pair_does_not_spread(tmp_path):
    gd_testhelpers.GATE["boom_prompt"] = "question number 2"
    result = run_ablation(_cfg(tmp_path / "p"), tmp_path / "o", concurrency=3)
    bad = [r for r in result.rows if r.outcome == "indeterminate"]
    assert sorted((r.id, r.variant) for r in bad) == [("i2", "G"), ("i2", "none")]
    assert all("RuntimeError" in (r.evidence or "") for r in bad)
    assert len(result.rows) == 12 and len((tmp_path / "o" / "results.jsonl").read_text().splitlines()) == 12


def test_interrupt_keeps_whole_lines_and_resume_matches_sequential(tmp_path):
    cfg = _cfg(tmp_path / "p")
    run_ablation(cfg, tmp_path / "ref")
    gd_testhelpers.reset_gate()
    gd_testhelpers.GATE["stop_prompt"] = "question number 3"
    out = tmp_path / "o"
    with pytest.raises(KeyboardInterrupt):
        run_ablation(cfg, out, concurrency=3)
    text = (out / "results.jsonl").read_text(encoding="utf-8")
    assert text == "" or text.endswith("\n")
    for line in text.splitlines():
        json.loads(line)  # every line on disk is complete
    gd_testhelpers.GATE["stop_prompt"] = None
    resumed = run_ablation(cfg, out, concurrency=3)
    ref = run_ablation(cfg, tmp_path / "ref2", fresh=True)
    assert (out / "results.jsonl").read_bytes() == (tmp_path / "ref" / "results.jsonl").read_bytes()
    assert resumed.summary == ref.summary  # meta differs (skipped_pairs), the numbers do not


@pytest.mark.parametrize("bad", [0, -1, 1.5, "2", True, None])
def test_library_rejects_bad_values(tmp_path, bad):
    with pytest.raises(ConfigError, match="concurrency must be a whole number >= 1"):
        run_ablation(_cfg(tmp_path / "p"), tmp_path / "o", concurrency=bad)


@pytest.mark.parametrize("bad", ["0", "-1", "1.5", "abc"])
def test_cli_rejects_bad_values_with_exit_2(tmp_path, capsys, bad):
    cfg = _cfg(tmp_path / "p")
    with pytest.raises(SystemExit) as e:
        main(["run", str(cfg), "--out", str(tmp_path / "o"), "--concurrency", bad])
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "--concurrency" in err and ("whole number >= 1" in err or "must be >= 1" in err)


def test_cli_help_and_run(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        main(["run", "--help"])
    assert e.value.code == 0 and "--concurrency" in capsys.readouterr().out
    cfg = str(_cfg(tmp_path / "p"))
    assert main(["run", cfg, "--out", str(tmp_path / "o1")]) == 0
    one = capsys.readouterr()
    assert main(["run", cfg, "--out", str(tmp_path / "o4"), "--concurrency", "4"]) == 0
    four = capsys.readouterr()
    assert one.out.replace("o1", "o") == four.out.replace("o4", "o") and one.err == "" == four.err  # simulated latency: no warning, same table


def test_measured_latency_warning_goes_to_stderr_only(tmp_path, capsys):
    cfg = str(_cfg(tmp_path / "p"))
    assert main(["run", cfg, "--out", str(tmp_path / "o"), "--latency", "measured", "--concurrency", "2"]) == 0
    cap = capsys.readouterr()
    assert cap.err.count("\n") == 1 and "measured latencies can be inflated" in cap.err
    assert "warning:" not in cap.out
    assert main(["run", cfg, "--out", str(tmp_path / "o2"), "--latency", "measured"]) == 0
    assert capsys.readouterr().err == ""
