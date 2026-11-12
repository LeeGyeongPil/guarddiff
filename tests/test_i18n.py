"""Output language: one message table, one decision rule, machine data unchanged."""

from __future__ import annotations

import gd_testhelpers  # noqa: F401  (importing it pins GUARDDIFF_LANG=en for this test file)

import re
import string
from pathlib import Path

import pytest

from conftest import item, write_project
from guarddiff import i18n
from guarddiff.cli import main
from guarddiff.i18n import MESSAGES, resolve_lang, scan_lang_option, t

ENV_NAMES = ("GUARDDIFF_LANG", "LC_ALL", "LC_MESSAGES", "LANG")


def _fields(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_languages_have_the_same_keys_and_placeholders():
    assert set(MESSAGES["en"]) == set(MESSAGES["ko"])
    for key, en_text in MESSAGES["en"].items():
        assert _fields(en_text) == _fields(MESSAGES["ko"][key]), key
        assert en_text.strip() and MESSAGES["ko"][key].strip(), key


def test_every_key_used_in_the_source_exists():
    src = Path(__file__).parent.parent / "src" / "guarddiff"
    used = set()
    for path in src.rglob("*.py"):
        used |= set(re.findall(r"\bt\(\s*\"([a-z_]+\.[a-z_.0-9]+)\"", path.read_text(encoding="utf-8")))
    assert used, "no t() calls found"
    used.discard("help.gate.")  # prefix; the five limit keys are checked below
    assert used <= set(MESSAGES["en"]), sorted(used - set(MESSAGES["en"]))
    # keys that are built at run time (gate limits, html column heads, md column heads)
    dynamic = {f"help.gate.{name}" for name in ("max_overblock", "min_asr_reduction", "max_p95_ms",
                                                "max_indeterminate", "max_cost_usd")}
    assert dynamic <= set(MESSAGES["en"])


def test_korean_uses_one_polite_style():
    """Messages end in the formal -ㅂ니다/-십시오 style; the informal -요 endings must not creep in."""
    informal = re.compile(r"(세요|해요|어요|아요|에요|예요|네요|죠|까요|래요|게요|나요)(?![가-힣])")
    texts = [*MESSAGES["ko"].values(), *i18n.ARGPARSE_KO.values()]
    bad = [text for text in texts if informal.search(text)]
    assert bad == []
    # the sentences really are in the formal style
    assert MESSAGES["ko"]["help.run"].endswith("수행합니다")
    assert MESSAGES["ko"]["config.not_found"].endswith("지정하십시오.")
    # most error messages are full sentences in the formal style (a few are short noun phrases)
    formal = [k for k, text in MESSAGES["ko"].items() if re.search(r"(니다|십시오)(?![가-힣])", text)]
    assert len(formal) > len(MESSAGES["ko"]) * 0.5


@pytest.mark.parametrize("env, expected", [
    ({}, "en"),
    ({"LANG": "C"}, "en"),
    ({"LANG": "POSIX"}, "en"),
    ({"LANG": "fr_FR.UTF-8"}, "en"),
    ({"LANG": "ko_KR.UTF-8"}, "ko"),
    ({"LANG": "ko"}, "ko"),
    ({"LANG": "KO_kr"}, "ko"),
    ({"LC_ALL": "ko_KR.UTF-8"}, "ko"),
    ({"LC_MESSAGES": "ko_KR.UTF-8"}, "ko"),
    ({"GUARDDIFF_LANG": "ko"}, "ko"),
    ({"GUARDDIFF_LANG": "klingon"}, "en"),
])
def test_resolve_lang_from_environment(env, expected):
    assert resolve_lang(None, env) == expected


def test_resolve_lang_precedence():
    ko = {"LANG": "ko_KR.UTF-8", "LC_MESSAGES": "ko_KR.UTF-8", "LC_ALL": "ko_KR.UTF-8", "GUARDDIFF_LANG": "ko"}
    # --lang beats everything
    assert resolve_lang("en", ko) == "en"
    assert resolve_lang("ko", {"GUARDDIFF_LANG": "en"}) == "ko"
    # GUARDDIFF_LANG beats LC_ALL, LC_ALL beats LC_MESSAGES, LC_MESSAGES beats LANG
    assert resolve_lang(None, {"GUARDDIFF_LANG": "en", "LC_ALL": "ko_KR.UTF-8"}) == "en"
    assert resolve_lang(None, {"LC_ALL": "en_US.UTF-8", "LC_MESSAGES": "ko_KR.UTF-8"}) == "en"
    assert resolve_lang(None, {"LC_MESSAGES": "C", "LANG": "ko_KR.UTF-8"}) == "en"
    assert resolve_lang(None, {"LC_ALL": "", "LANG": "ko_KR.UTF-8"}) == "ko"  # empty = not set
    # an invalid --lang value is ignored here (argparse rejects it); the environment decides
    assert resolve_lang("fr", {"LANG": "ko_KR.UTF-8"}) == "ko"


def test_scan_lang_option_finds_it_anywhere():
    assert scan_lang_option(["--lang", "ko", "demo"]) == "ko"
    assert scan_lang_option(["demo", "--lang=ko"]) == "ko"
    assert scan_lang_option(["gate", "x", "--lang", "en", "--lang", "ko"]) == "ko"
    assert scan_lang_option(["demo", "--", "--lang", "ko"]) is None
    assert scan_lang_option(["demo"]) is None
    assert scan_lang_option(["demo", "--lang"]) is None


def test_t_follows_the_environment_and_main_restores_it(clean_env):
    assert t("init.wrote", path="a") == "wrote a"
    clean_env.setenv("GUARDDIFF_LANG", "ko")
    assert t("init.wrote", path="a") == "작성했습니다: a"
    clean_env.setenv("GUARDDIFF_LANG", "en")
    assert t("init.wrote", path="a") == "wrote a"
    assert i18n._override is None


def test_flag_beats_environment_and_does_not_leak(tmp_path, capsys, clean_env):
    clean_env.setenv("GUARDDIFF_LANG", "en")
    assert main(["init", str(tmp_path / "a"), "--lang", "ko"]) == 0
    out = capsys.readouterr().out
    assert "작성했습니다" in out and "wrote" not in out
    assert i18n._override is None
    # argparse's patched gettext is restored too
    import argparse
    assert argparse._("usage: ") == "usage: "
    assert main(["init", str(tmp_path / "b")]) == 0
    assert "wrote" in capsys.readouterr().out


def test_lang_flag_before_the_subcommand(tmp_path, capsys, clean_env):
    assert main(["--lang", "ko", "init", str(tmp_path / "a")]) == 0
    assert "작성했습니다" in capsys.readouterr().out


def test_environment_decides_without_flag(tmp_path, capsys, clean_env):
    clean_env.setenv("LANG", "ko_KR.UTF-8")
    assert main(["init", str(tmp_path / "a")]) == 0
    assert "작성했습니다" in capsys.readouterr().out
    clean_env.setenv("GUARDDIFF_LANG", "en")  # beats LANG
    assert main(["init", str(tmp_path / "b")]) == 0
    assert "wrote" in capsys.readouterr().out


def test_demo_in_korean(tmp_path, capsys):
    assert main(["--lang", "ko", "demo", "--out", str(tmp_path / "d")]) == 0
    out = capsys.readouterr().out
    assert "연습용 목(mock) 대상입니다" in out
    assert "시뮬레이션 지연입니다" in out
    assert "기준=none" in out and "결과:" in out and "보고서:" in out
    assert "McNemar p" in out  # metric names stay as they are


def test_gate_in_korean(tmp_path, capsys):
    main(["demo", "--out", str(tmp_path / "d")])
    capsys.readouterr()
    summary = str(tmp_path / "d" / "out" / "summary.json")
    assert main(["gate", summary, "--variant", "B", "--max-overblock", "0.5", "--lang", "ko"]) == 0
    assert "게이트를 통과했습니다" in capsys.readouterr().out
    assert main(["gate", summary, "--variant", "B", "--max-overblock", "-1", "--lang", "ko"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("오류: ") and "0 이상의 숫자" in err
    assert main(["gate", summary, "--variant", "B", "--lang", "ko"]) == 2
    assert "한도를 하나 이상 지정하십시오" in capsys.readouterr().err
    assert main(["gate", summary, "--variant", "B", "--min-asr-reduction", "2", "--lang", "ko"]) == 1
    out = capsys.readouterr().out
    assert "게이트에서 실패했습니다" in out and "asr_reduction_vs_none" in out  # metric names are data


def test_init_exists_error_in_korean(tmp_path, capsys):
    main(["init", str(tmp_path)])
    capsys.readouterr()
    assert main(["init", str(tmp_path), "--lang", "ko"]) == 2
    err = capsys.readouterr().err
    assert "이미 있습니다" in err and "--force" in err


def test_missing_config_is_a_korean_error_with_exit_2(tmp_path, capsys):
    assert main(["run", str(tmp_path / "nope.toml"), "--lang", "ko"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("오류: 설정 파일을 찾을 수 없습니다")
    assert main(["run", str(tmp_path / "nope.toml")]) == 2
    assert capsys.readouterr().err.startswith("error: config file not found")


def test_library_errors_follow_the_language(tmp_path, monkeypatch):
    from guarddiff import load_config
    from guarddiff.errors import ConfigError

    with pytest.raises(ConfigError, match="config file not found"):
        load_config(tmp_path / "x.toml")
    monkeypatch.setenv("GUARDDIFF_LANG", "ko")
    with pytest.raises(ConfigError, match="설정 파일을 찾을 수 없습니다"):
        load_config(tmp_path / "x.toml")


def test_help_in_korean(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--lang", "ko", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "사용법:" in out and "옵션" in out and "도움말을 보여 주고 종료합니다" in out
    assert "같은 프롬프트로 가드레일을 끈 경우와 켠 경우를 비교합니다." in out
    assert "usage:" not in out and "show this help" not in out
    with pytest.raises(SystemExit):
        main(["gate", "--lang", "ko", "-h"])
    out = capsys.readouterr().out
    assert "위치 인자" in out and "--max-overblock" in out and "정상 프롬프트 비율" in out


def test_help_in_english(capsys):
    with pytest.raises(SystemExit):
        main(["--lang", "en", "run", "--help"])
    out = capsys.readouterr().out
    assert "usage:" in out and "--concurrency" in out and "--lang" in out


def test_invalid_lang_value_is_a_localized_choices_error(capsys, clean_env):
    with pytest.raises(SystemExit) as exc:
        main(["--lang", "fr", "demo"])
    assert exc.value.code == 2
    assert "invalid choice: 'fr'" in capsys.readouterr().err
    clean_env.setenv("GUARDDIFF_LANG", "ko")
    with pytest.raises(SystemExit) as exc:
        main(["--lang", "fr", "demo"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "오류:" in err and "잘못된 선택입니다" in err and "인자 --lang" in err


def test_argparse_errors_in_korean(capsys):
    cases = [
        (["--lang", "ko"], "다음 인자가 필요합니다"),                       # sub-command missing
        (["--lang", "ko", "run"], "다음 인자가 필요합니다: config"),         # positional missing
        (["--lang", "ko", "bogus"], "잘못된 선택입니다"),                    # invalid sub-command
        (["--lang", "ko", "report", "d", "--format", "xml"], "잘못된 선택입니다"),
        (["--lang", "ko", "demo", "--nope"], "알 수 없는 인자입니다: --nope"),
        (["--lang", "ko", "run", "c.toml", "--concurrency", "0"], "1 이상이어야 합니다"),
        (["--lang", "ko", "run", "c.toml", "--concurrency", "x"], "1 이상의 정수여야 합니다"),
        (["--lang", "ko", "gate", "s.json", "--variant", "A", "--max-p95-ms", "abc"], "float 값이 올바르지 않습니다"),
        (["--lang", "ko", "run", "c.toml", "--out"], "인자가 하나 필요합니다"),
    ]
    for argv, expected in cases:
        with pytest.raises(SystemExit) as exc:
            main(argv)
        assert exc.value.code == 2, argv
        err = capsys.readouterr().err
        assert "오류:" in err and expected in err, (argv, err)
        assert "error:" not in err and "usage:" not in err, (argv, err)


def test_argparse_errors_stay_english_by_default(capsys, clean_env):
    with pytest.raises(SystemExit):
        main(["run"])
    err = capsys.readouterr().err
    assert "the following arguments are required: config" in err and "error:" in err


def test_concurrency_warning_in_korean(tmp_path, capsys):
    cfg = write_project(tmp_path, items=[item("a1", "attack", "x"), item("b1", "benign", "y")],
                        toml='[run]\nitems = "items.jsonl"\n[[variants]]\nname = "none"\nguards = []\n')
    assert main(["run", str(cfg), "--out", str(tmp_path / "o"), "--latency", "measured", "--concurrency", "2",
                 "--lang", "ko"]) == 0
    err = capsys.readouterr().err
    assert err.startswith("경고: ") and "--concurrency > 1" in err


def test_json_report_and_data_files_are_identical_in_both_languages(tmp_path, capsys):
    out_en, out_ko = tmp_path / "en", tmp_path / "ko"
    assert main(["demo", "--out", str(out_en), "--lang", "en"]) == 0
    assert main(["demo", "--out", str(out_ko), "--lang", "ko"]) == 0
    capsys.readouterr()
    for name in ("results.jsonl", "summary.json"):
        assert (out_en / "out" / name).read_bytes() == (out_ko / "out" / name).read_bytes(), name
    assert main(["report", str(out_en / "out"), "--format", "json", "--lang", "en"]) == 0
    json_en = capsys.readouterr().out
    assert main(["report", str(out_en / "out"), "--format", "json", "--lang", "ko"]) == 0
    json_ko = capsys.readouterr().out
    assert json_en.encode("utf-8") == json_ko.encode("utf-8")
    assert json_en.strip().startswith("{")


def test_failure_strings_stored_in_results_are_not_translated(tmp_path, capsys):
    """results.jsonl is data: a guard that raises stores the same failure text in every language."""
    cfg = write_project(
        tmp_path, items=[item("a1", "attack", "x")],
        toml='[run]\nitems = "items.jsonl"\n[[guards]]\nname = "g"\ntype = "python"\n'
             'callable = "gd_testhelpers:flaky_guard"\n[[variants]]\nname = "none"\nguards = []\n'
             '[[variants]]\nname = "G"\nguards = ["g"]\n')
    gd_testhelpers.FLAKY["guard"] = True
    try:
        assert main(["run", str(cfg), "--out", str(tmp_path / "en"), "--lang", "en"]) == 0
        assert main(["run", str(cfg), "--out", str(tmp_path / "ko"), "--lang", "ko"]) == 0
    finally:
        gd_testhelpers.FLAKY["guard"] = False
    capsys.readouterr()
    assert (tmp_path / "en" / "results.jsonl").read_bytes() == (tmp_path / "ko" / "results.jsonl").read_bytes()


def test_reports_in_korean_keep_the_same_structure(tmp_path, capsys):
    main(["demo", "--out", str(tmp_path / "d")])
    out = tmp_path / "d" / "out"
    capsys.readouterr()
    assert main(["report", str(out), "--format", "md", "--lang", "ko"]) == 0
    md_ko = capsys.readouterr().out
    assert main(["report", str(out), "--format", "md", "--lang", "en"]) == 0
    md_en = capsys.readouterr().out
    assert "## guarddiff 보고서" in md_ko and "| 변형 |" in md_ko and "기준 변형: `none`" in md_ko
    assert "## guarddiff report" in md_en and "| variant |" in md_en
    assert len(md_ko.splitlines()) == len(md_en.splitlines())

    main(["report", str(out), "--lang", "ko"])
    html_ko = (out / "report.html").read_text(encoding="utf-8")
    main(["report", str(out), "--lang", "en"])
    html_en = (out / "report.html").read_text(encoding="utf-8")
    assert '<html lang="ko">' in html_ko and '<html lang="en">' in html_en
    assert "<title>guarddiff 보고서</title>" in html_ko and "<h2>요약</h2>" in html_ko
    assert "<h2>항목별 결과</h2>" in html_ko and "<h2>Summary</h2>" in html_en

    def tags(text: str) -> list[str]:
        return re.findall(r"<(/?[a-z0-9]+)(?:\s+class=\"[^\"]*\")?", text)

    assert tags(html_ko) == tags(html_en)  # same element structure, so screenshot selectors work in both
    for cls in ("note", "o-blocked", "o-missed"):
        assert html_ko.count(f'class="{cls}"') == html_en.count(f'class="{cls}"')
