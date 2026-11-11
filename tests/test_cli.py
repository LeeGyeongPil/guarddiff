"""AC-2 and AC-3: demo and gate commands. Plus the error boundaries (empty, malformed, missing)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import item, write_project
from guarddiff.cli import main

MINIMAL_TOML = """
[run]
items = "items.jsonl"
[[variants]]
name = "none"
guards = []
"""


def test_demo_command_outputs(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code = main(["demo", "--out", "guarddiff-demo"])
    out = capsys.readouterr().out
    assert code == 0
    assert "practice mock" in out and "simulated latency" in out
    rows = {line.split()[0]: line.split() for line in out.splitlines() if line.split()[:1] in (["none"], ["A"], ["B"])}
    assert set(rows) == {"none", "A", "B"}
    assert rows["A"][1] == "0.222" and rows["A"][4] == "0.667"  # ASR, overblock
    assert rows["B"][1] == "0.000"
    folder = tmp_path / "guarddiff-demo" / "out"
    assert len((folder / "results.jsonl").read_text(encoding="utf-8").splitlines()) == 54
    assert (folder / "summary.json").is_file() and (folder / "report.html").is_file()


def test_gate_exit_codes(offline_dir, tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["run", str(offline_dir / "guarddiff.toml"), "--out", str(out)]) == 0
    summary = str(out / "summary.json")
    capsys.readouterr()

    assert main(["gate", summary, "--variant", "A", "--max-overblock", "0.2"]) == 1
    assert "guard_overblock_rate 0.6667 > 0.2" in capsys.readouterr().out

    assert main(["gate", summary, "--variant", "B", "--max-overblock", "0.2", "--min-asr-reduction", "0.3",
                 "--max-p95-ms", "500"]) == 0
    capsys.readouterr()

    assert main(["gate", summary, "--variant", "nope", "--max-overblock", "0.2"]) == 2
    assert "nope" in capsys.readouterr().err

    # several failures are listed one per line, with the direction of each comparison
    assert main(["gate", summary, "--variant", "A", "--max-overblock", "0.2", "--min-asr-reduction", "0.9",
                 "--max-cost-usd", "0"]) == 1
    text = capsys.readouterr().out
    assert "asr_reduction_vs_none 0.4445 < 0.9" in text and "guard_overblock_rate 0.6667 > 0.2" in text


def test_gate_input_errors(offline_dir, tmp_path, capsys):
    assert main(["gate", str(tmp_path / "missing.json"), "--variant", "A", "--max-overblock", "0.2"]) == 2
    assert "summary file not found" in capsys.readouterr().err
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert main(["gate", str(bad), "--variant", "A", "--max-overblock", "0.2"]) == 2
    assert "not valid JSON" in capsys.readouterr().err
    out = tmp_path / "out"
    main(["run", str(offline_dir / "guarddiff.toml"), "--out", str(out)])
    capsys.readouterr()
    assert main(["gate", str(out / "summary.json"), "--variant", "A"]) == 2  # no limit given
    assert "at least one limit" in capsys.readouterr().err
    assert main(["gate", str(out / "summary.json"), "--variant", "A", "--max-overblock", "-1"]) == 2
    assert ">= 0" in capsys.readouterr().err


def test_run_only_resume_and_report_formats(offline_dir, tmp_path, capsys):
    out = tmp_path / "out"
    cfg = str(offline_dir / "guarddiff.toml")
    assert main(["run", cfg, "--out", str(out), "--only", "B"]) == 0  # baseline "none" is added automatically
    assert len((out / "results.jsonl").read_text(encoding="utf-8").splitlines()) == 36
    assert main(["run", cfg, "--out", str(out), "--only", "Z"]) == 2
    assert "unknown variant" in capsys.readouterr().err
    capsys.readouterr()
    assert main(["run", cfg, "--out", str(out)]) == 0
    assert "resumed_from_file=36" in capsys.readouterr().out

    assert main(["report", str(out), "--format", "md"]) == 0
    md = capsys.readouterr().out
    assert len([ln for ln in md.splitlines() if ln.startswith("| ") and "variant" not in ln]) == 3
    assert main(["report", str(out), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["A"]["asr"] == 0.2222
    assert main(["report", str(out)]) == 0
    assert (out / "report.html").is_file()
    assert main(["report", str(tmp_path / "empty-dir")]) == 2
    assert "Run `guarddiff run" in capsys.readouterr().err


def test_init_copies_example_and_refuses_to_overwrite(tmp_path, capsys):
    dest = tmp_path / "mine"
    assert main(["init", str(dest)]) == 0
    assert (dest / "guarddiff.toml").is_file() and (dest / "items.jsonl").is_file()
    capsys.readouterr()
    assert main(["init", str(dest)]) == 2
    assert "--force" in capsys.readouterr().err
    assert main(["init", str(dest), "--force"]) == 0


def test_empty_items_file_is_a_clear_error(tmp_path, capsys):
    cfg = write_project(tmp_path / "p", items=[], toml=MINIMAL_TOML)
    assert main(["run", str(cfg), "--out", str(tmp_path / "o")]) == 2
    assert "no items found" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{broken\n", "invalid JSON"),
        ('["a"]\n', "expected a JSON object"),
        ('{"id": "a", "label": "evil", "prompt": "x"}\n', "label must be 'attack' or 'benign'"),
        ('{"id": "a", "label": "attack"}\n', "'prompt' is required"),
        ('{"id": "a", "label": "attack", "prompt": "x"}\n{"id": "a", "label": "benign", "prompt": "y"}\n',
         "duplicate id"),
    ],
)
def test_bad_items_lines_name_the_line(tmp_path, capsys, content, message):
    cfg = write_project(tmp_path / "p", items=[item("a", "attack", "x")], toml=MINIMAL_TOML)
    (tmp_path / "p" / "items.jsonl").write_text(content, encoding="utf-8")
    assert main(["run", str(cfg), "--out", str(tmp_path / "o")]) == 2
    err = capsys.readouterr().err
    assert message in err and "items.jsonl:" in err


@pytest.mark.parametrize(
    ("toml", "message"),
    [
        ("[run\nitems = 'x'", "invalid TOML"),
        ('[run]\nitems = "items.jsonl"\n', "at least one [[variants]]"),
        ('[run]\n[[variants]]\nname = "none"\n', "[run].items is required"),
        (MINIMAL_TOML + '[[guards]]\nname = "g"\ntype = "magic"\n', "unknown type 'magic'"),
        (MINIMAL_TOML + '[[guards]]\nname = "g"\ntype = "regex"\nstage = "tool"\npatterns = ["x"]\n',
         "tool stage is planned for a later release"),
        (MINIMAL_TOML + '[[guards]]\nname = "g"\ntype = "regex"\npatterns = ["("]\n', "invalid regex"),
        (MINIMAL_TOML + '[[variants]]\nname = "v"\nguards = ["ghost"]\n', "unknown guard(s) ['ghost']"),
        (MINIMAL_TOML.replace("[run]", '[run]\nlatency = "fast"'), "must be 'simulated' or 'measured'"),
        (MINIMAL_TOML + "[target]\ntype = 'telepathy'\n", "unknown type 'telepathy'"),
    ],
)
def test_bad_config_exits_2_with_hint(tmp_path, capsys, toml, message):
    cfg = write_project(tmp_path / "p", items=[item("a", "attack", "x")], toml=toml)
    # guards listed in the config are only built when a variant uses them, so use them
    if "[[guards]]" in toml and 'name = "v"' not in toml:
        cfg.write_text(toml + '[[variants]]\nname = "g1"\nguards = ["g"]\n', encoding="utf-8")
    assert main(["run", str(cfg), "--out", str(tmp_path / "o")]) == 2
    assert message in capsys.readouterr().err


def test_missing_config_and_items_files(tmp_path, capsys):
    assert main(["run", str(tmp_path / "nope.toml"), "--out", str(tmp_path / "o")]) == 2
    assert "config file not found" in capsys.readouterr().err
    cfg = write_project(tmp_path / "p", items=[item("a", "attack", "x")], toml=MINIMAL_TOML)
    (tmp_path / "p" / "items.jsonl").unlink()
    assert main(["run", str(cfg), "--out", str(tmp_path / "o")]) == 2
    assert "items file not found" in capsys.readouterr().err


def test_non_utf8_config_is_reported(tmp_path, capsys):
    cfg = tmp_path / "bad.toml"
    cfg.write_bytes(b"\xff\xfe\x00broken")
    assert main(["run", str(cfg), "--out", str(tmp_path / "o")]) == 2
    assert "UTF-8" in capsys.readouterr().err


def test_python_module_entry_point_runs(tmp_path):
    import subprocess
    import sys

    res = subprocess.run([sys.executable, "-m", "guarddiff", "--version"], capture_output=True, text=True,
                         timeout=60, cwd=Path(tmp_path))
    assert res.returncode == 0 and res.stdout.startswith("guarddiff ")
