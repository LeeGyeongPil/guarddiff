"""AC-9: the HTML report is one self-contained file and shows every item x variant with its evidence."""

from __future__ import annotations

import json
import re

from conftest import FIXTURES, item, write_project
from guarddiff import run_ablation
from guarddiff.cli import main


def test_html_report_contents(offline_dir, tmp_path, capsys):
    out = tmp_path / "out"
    run_ablation(offline_dir / "guarddiff.toml", out)
    page = (out / "report.html").read_text(encoding="utf-8")

    ids = [json.loads(ln)["id"] for ln in (FIXTURES / "items.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(ids) == 18
    for i in ids:
        row = re.search(rf"<tr><td>{i}</td>.*?</tr>", page)
        assert row, i
        assert len(re.findall(r'class="o-', row.group(0))) == 3  # one outcome cell per variant
    assert "95% CI" in page and "McNemar p" in page
    assert "0.3542&ndash;0.8794" in page  # Wilson interval of none's ASR
    assert "0.03125" in page  # B's McNemar p
    assert "A-keyword: regex" in page  # evidence strings are shown
    assert "simulated latency" in page and "practice mock" in page
    assert not re.search(r"https?://", page)  # no external resources, no links
    assert "<script" not in page and "<link" not in page

    # CI summary table
    assert main(["report", str(out), "--format", "md"]) == 0
    md = capsys.readouterr().out
    table_rows = [ln for ln in md.splitlines() if ln.startswith("| ") and not ln.startswith("| variant")]
    assert [ln.split("|")[1].strip() for ln in table_rows] == ["none", "A", "B"]
    assert "simulated latency" in md and "practice mock" in md


def test_prompts_and_evidence_are_escaped(tmp_path):
    evil = '<script>alert("x")</script> bomb & <img src=x onerror=1>'
    toml = """
[run]
items = "items.jsonl"
[[guards]]
name = "g<b>"
type = "regex"
patterns = ['<script>']
sim_latency_ms = 1.0
[[variants]]
name = "none"
guards = []
[[variants]]
name = "v&w"
guards = ["g<b>"]
"""
    result = run_ablation(write_project(tmp_path / "p", items=[item("x<1>", "attack", evil)], toml=toml),
                          tmp_path / "out")
    page = (tmp_path / "out" / "report.html").read_text(encoding="utf-8")
    assert "&lt;script&gt;" in page and "<script>" not in page
    assert "<img" not in page and "&amp;" in page
    assert "x&lt;1&gt;" in page and "v&amp;w" in page and "g&lt;b&gt;" in page
    assert result.rows_for("v&w")[0].outcome == "blocked"
