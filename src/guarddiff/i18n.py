"""Output language (English / Korean): one message table, one language decision.

Order of precedence: ``--lang en|ko`` > ``GUARDDIFF_LANG`` > ``LC_ALL`` > ``LC_MESSAGES`` > ``LANG``.
The first of these variables that is set and not empty decides: a value starting with ``ko`` means Korean,
anything else (``C``, ``POSIX``, ``fr_FR``, a typo) means English.

Only text meant for people is translated. Machine data (``results.jsonl``, ``summary.json``, ``report --format
json``, failure strings stored in results) is the same in every language.
"""

from __future__ import annotations

import argparse
import os
from contextlib import contextmanager
from typing import Iterator, Mapping, Sequence

LANGS = ("en", "ko")
ENV_VARS = ("GUARDDIFF_LANG", "LC_ALL", "LC_MESSAGES", "LANG")

# Set by the CLI for the duration of one `main()` call (see `use_lang`). None = decide from the environment.
_override: str | None = None


def _from_value(value: str) -> str:
    return "ko" if value.strip().lower().startswith("ko") else "en"


def resolve_lang(argv_lang: str | None = None, environ: Mapping[str, str] | None = None) -> str:
    """Return ``"en"`` or ``"ko"``. ``argv_lang`` is the value of ``--lang`` when it was given."""
    if argv_lang in LANGS:
        return str(argv_lang)
    env = os.environ if environ is None else environ
    for name in ENV_VARS:
        value = env.get(name, "")
        if value.strip():
            return _from_value(value)
    return "en"


def scan_lang_option(argv: Sequence[str]) -> str | None:
    """Find ``--lang X`` or ``--lang=X`` anywhere in ``argv`` (before ``--``); the last one wins."""
    found: str | None = None
    items = list(argv)
    for pos, arg in enumerate(items):
        if arg == "--":
            break
        if arg == "--lang" and pos + 1 < len(items):
            found = items[pos + 1]
        elif arg.startswith("--lang="):
            found = arg.split("=", 1)[1]
    return found


def current_lang() -> str:
    return _override if _override is not None else resolve_lang()


@contextmanager
def use_lang(lang: str) -> Iterator[None]:
    """Make ``t()`` (and argparse's own messages) use ``lang`` inside the ``with`` block."""
    global _override
    previous = _override
    _override = lang
    saved = (getattr(argparse, "_"), getattr(argparse, "ngettext"))
    argparse._ = _argparse_text  # type: ignore[attr-defined]
    argparse.ngettext = _argparse_ngettext  # type: ignore[attr-defined]
    try:
        yield
    finally:
        _override = previous
        argparse._, argparse.ngettext = saved  # type: ignore[attr-defined]


def t(message_id: str, /, **kw: object) -> str:
    """The message ``message_id`` in the current language, filled with ``kw`` (``key`` is a valid placeholder)."""
    table = MESSAGES[current_lang()]
    return table[message_id].format(**kw) if kw else table[message_id]


def _argparse_text(msg: str) -> str:
    """Stand-in for the gettext function argparse uses. Unknown messages stay English."""
    if current_lang() == "ko":
        return ARGPARSE_KO.get(msg, msg)
    return msg


def _argparse_ngettext(singular: str, plural: str, n: int) -> str:
    if current_lang() == "ko":
        return ARGPARSE_KO.get(singular, singular)
    return singular if n == 1 else plural


# argparse's own messages (msgid -> Korean). Messages not listed here fall back to English.
ARGPARSE_KO: dict[str, str] = {
    "usage: ": "사용법: ",
    "positional arguments": "위치 인자",
    "options": "옵션",
    "subcommands": "하위 명령",
    "show this help message and exit": "도움말을 보여 주고 종료합니다",
    "show program's version number and exit": "버전을 보여 주고 종료합니다",
    " (default: %(default)s)": " (기본값: %(default)s)",
    "%(prog)s: error: %(message)s\n": "%(prog)s: 오류: %(message)s\n",
    "%(prog)s: warning: %(message)s\n": "%(prog)s: 경고: %(message)s\n",
    "argument %(argument_name)s: %(message)s": "인자 %(argument_name)s: %(message)s",
    "the following arguments are required: %s": "다음 인자가 필요합니다: %s",
    "unrecognized arguments: %s": "알 수 없는 인자입니다: %s",
    "invalid choice: %(value)r (choose from %(choices)s)": "잘못된 선택입니다: %(value)r (선택 가능: %(choices)s)",
    "invalid choice: %(value)r, maybe you meant %(closest)r? (choose from %(choices)s)":
        "잘못된 선택입니다: %(value)r, %(closest)r 를 의도하셨습니까? (선택 가능: %(choices)s)",
    "invalid %(type)s value: %(value)r": "%(type)s 값이 올바르지 않습니다: %(value)r",
    "expected one argument": "인자가 하나 필요합니다",
    "expected at most one argument": "인자는 최대 하나만 받을 수 있습니다",
    "expected at least one argument": "인자가 하나 이상 필요합니다",
    "expected %s argument": "인자가 %s개 필요합니다",
    "ignored explicit argument %r": "지정한 값 %r 는 이 옵션에서 쓸 수 없습니다",
    "unexpected option string: %s": "예상하지 못한 옵션입니다: %s",
    "ambiguous option: %(option)s could match %(matches)s": "모호한 옵션입니다: %(option)s 는 %(matches)s 와 일치할 수 있습니다",
    "unknown parser %(parser_name)r (choices: %(choices)s)":
        "알 수 없는 하위 명령입니다: %(parser_name)r (선택 가능: %(choices)s)",
    "not allowed with argument %s": "인자 %s 와 함께 쓸 수 없습니다",
    "one of the arguments %s is required": "다음 인자 중 하나가 필요합니다: %s",
    "%(heading)s:": "%(heading)s:",
}

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        # ---- command line: help text
        "cli.description": "Compare guardrails off vs on with the same prompts.",
        "cli.lang_help": "output language: en or ko (default: GUARDDIFF_LANG, then LC_ALL / LC_MESSAGES / LANG, "
                         "otherwise en)",
        "help.run": "run the ablation from a TOML config",
        "help.report": "rebuild a report from an output folder",
        "help.gate": "exit 1 when a variant breaks a limit (for CI)",
        "help.demo": "copy the offline example and run it (practice mock, no network)",
        "help.init": "copy the example config and prompts to edit",
        "help.run.config": "path to the guarddiff TOML config",
        "help.run.out": "output folder (default: guarddiff-out)",
        "help.run.latency": "override [run].latency from the config",
        "help.run.fresh": "do not reuse earlier results; run every pair of the selected variants again",
        "help.run.only": "run only these variants (plus the baseline); results of the other variants are kept",
        "help.run.concurrency": "run N (item, variant) pairs at the same time (default 1 = one after another)",
        "help.report.dir": "output folder written by `run`",
        "help.report.format": "report format (default: html)",
        "help.gate.summary": "summary.json written by `run`",
        "help.gate.variant": "the variant to check",
        "help.gate.max_overblock": "fail when the share of benign prompts the guard blocked is above X",
        "help.gate.min_asr_reduction": "fail when the ASR reduction versus the baseline is below X",
        "help.gate.max_p95_ms": "fail when the guard's p95 latency (ms) is above X",
        "help.gate.max_indeterminate": "fail when the share of failed items is above X (default: 0)",
        "help.gate.max_cost_usd": "fail when the total guard cost (USD) is above X",
        "help.gate.allow_indeterminate": "do not fail on guard/target failures (default: any indeterminate item "
                                         "fails the gate; use --max-indeterminate X to allow a share). Cannot be "
                                         "combined with --max-indeterminate",
        "help.demo.out": "folder to copy the example into (default: guarddiff-demo)",
        "help.init.dir": "folder to write the files into (default: current folder)",
        "help.init.force": "overwrite existing files",
        "cli.error_prefix": "error",
        # ---- command line: output
        "run.baseline_line": "baseline={baseline}  pairs={pairs}  resumed_from_file={resumed}",
        "run.rerun": "rerun {n} pairs (config changed)",
        "run.retry": "retry {n} indeterminate pairs (they failed last time)",
        "run.kept": "kept {n} pairs of variants not run this time: {variants}",
        "run.paths": "results: {results}\nsummary: {summary}\nreport:  {report}",
        "run.warn_concurrency": "warning: --concurrency > 1 with measured latency: calls overlap, so measured "
                                "latencies can be inflated. Use simulated latency to compare guards.\n",
        "gate.failed": "gate FAILED for variant {variant!r}:",
        "gate.passed": "gate passed for variant {variant!r}",
        "gate.note_allowed": "note: indeterminate_rate {rate} was allowed by the options given. Failed items are "
                             "not counted as missed attacks.",
        "gate.need_limit": "give at least one limit: {options}.",
        "gate.exclusive": "--allow-indeterminate and --max-indeterminate cannot be used together. Give "
                          "--max-indeterminate X to allow a share of failed items, or --allow-indeterminate "
                          "to switch the check off.",
        "init.wrote": "wrote {path}",
        "init.next": "Edit guarddiff.toml and items.jsonl, then run `guarddiff run guarddiff.toml --out out`.",
        "init.exists": "{paths} already exist(s). Pass --force to overwrite, or choose another folder.",
        "arg.concurrency_type": "must be a whole number >= 1, got {value!r}",
        "arg.concurrency_min": "must be >= 1 (1 = one pair at a time), got {value}",
        # ---- table / report headings
        "table.variant": "variant",
        "report.title": "guarddiff report",
        "report.summary": "Summary",
        "report.per_item": "Per item",
        "report.notice_mock": "practice mock target (not a real LLM)",
        "report.notice_simulated": "simulated latency (reproducible placeholder values, not measurements)",
        "report.asr_reduction_the": "the ASR reduction",
        "report.warn_indeterminate": "indeterminate items (a guard or the target failed) in: {variants}. They are "
                                     "not counted as missed attacks, so {reduction} may look better than it is. "
                                     "Fix the failures, or run `guarddiff gate`.",
        "md.variant": "variant",
        "md.asr": "ASR (95% CI)",
        "md.asr_reduction": "ASR reduction",
        "md.overblock": "overblock (95% CI)",
        "md.indeterminate": "indeterminate",
        "md.p50": "p50 ms",
        "md.p95": "p95 ms",
        "md.cost": "cost USD",
        "md.mcnemar": "McNemar p",
        "md.baseline": "Baseline variant: `{baseline}`. Rates use all items of a label as the denominator.",
        "html.baseline": "Baseline: <b>{baseline}</b>. Rates use all items of a label as the denominator "
                         "(indeterminate included). Intervals are Wilson 95%; the paired p is an exact McNemar "
                         "test.",
        "html.variant": "variant",
        "html.n": "n atk / ben",
        "html.asr": "ASR",
        "html.asr_ci": "ASR 95% CI",
        "html.asr_reduction": "ASR reduction",
        "html.overblock": "overblock",
        "html.overblock_ci": "overblock 95% CI",
        "html.total_overrefusal": "total overrefusal",
        "html.indeterminate": "indeterminate",
        "html.latency": "latency p50 / p95 ms",
        "html.cost": "cost USD",
        "html.calls": "target calls",
        "html.fixed": "fixed / regressed",
        "html.mcnemar": "McNemar p",
        "html.redundant": "redundant blocks",
        "html.id": "id",
        "html.label": "label",
        "html.prompt": "prompt",
        "html.outcomes": "Outcomes: {outcomes}.",
        # ---- errors: config
        "config.not_found": "config file not found: {path}. Create one with `guarddiff init` or pass the right "
                            "path.",
        "config.bad_toml": "{path}: invalid TOML ({detail}).",
        "config.not_utf8": "{path}: the file must be UTF-8 text ({detail}).",
        "config.unknown_top": "{where}: unknown top-level key(s) {unknown}. Allowed: {allowed}.",
        "config.run_keys": "{where}: [run] may only contain {allowed}.",
        "config.items_required": "{where}: [run].items is required, for example items = \"items.jsonl\".",
        "config.latency": "{where}: [run].latency must be 'simulated' or 'measured', got {value!r}.",
        "config.guards_tables": "{where}: guards must be written as [[guards]] tables.",
        "config.dup_guards": "{where}: duplicate guard name(s) {names}. Names must be unique.",
        "config.no_variants": "{where}: add at least one [[variants]] table (name + guards list), for example "
                              "name = \"none\" and guards = [].",
        "config.variant_name": "{where}: every [[variants]] entry needs a 'name'.",
        "config.variant_guards": "{where}: variant '{variant}': guards must be a list of guard names.",
        "config.variant_unknown_guard": "{where}: variant '{variant}' uses unknown guard(s) {missing}. Defined "
                                        "guards: {defined}.",
        "config.dup_variants": "{where}: duplicate variant names in {names}.",
        "config.baseline": "{where}: [run].baseline {value!r} is not one of the variants {names}.",
        "config.tables": "{where}: [target] and [judge] must be tables.",
        "config.judge_type": "{where}: [judge].type {value!r} is not supported yet; use 'rules'.",
        # ---- errors: items
        "items.not_found": "items file not found: {path}. Set [run].items in your config to an existing .jsonl "
                           "file.",
        "items.bad_json": "{where}: invalid JSON ({detail}). Each line must be one JSON object.",
        "items.not_object": "{where}: expected a JSON object, got {type}.",
        "items.field": "{where}: field '{key}' is required and must be a non-empty string.",
        "items.label": "{where}: label must be 'attack' or 'benign', got {value!r}.",
        "items.dup_id": "{where}: duplicate id {value!r}. Ids must be unique.",
        "items.empty": "no items found in {path}. Add at least one line like {example}.",
        # ---- errors: gate
        "gate.summary_not_found": "summary file not found: {path}. Run `guarddiff run CONFIG --out DIR` and pass "
                                  "DIR/summary.json.",
        "gate.summary_bad_json": "{path}: not valid JSON ({detail}). Pass the summary.json written by `guarddiff "
                                 "run`.",
        "gate.summary_not_object": "{path}: expected a JSON object.",
        "gate.unknown_variant": "variant {variant!r} is not in the summary. Available: {available}.",
        "gate.unknown_limit": "unknown gate limit {name!r}. Use: {allowed}.",
        "gate.bad_limit": "{name} must be a number >= 0, got {value!r}.",
        "gate.no_metric": "{key} is not available for variant {variant!r} in this summary.",
        # ---- errors: runner
        "runner.only_unknown": "--only: unknown variant(s) {unknown}. Defined variants: {names}.",
        "runner.concurrency": "concurrency must be a whole number >= 1 (1 = one pair at a time), got {value!r}.",
        "runner.latency": "latency must be 'simulated' or 'measured', got {value!r}.",
        "runner.no_results": "{path} not found. Run `guarddiff run CONFIG --out {out}` first.",
        "runner.no_rows": "{path} has no readable rows. Re-run with --fresh.",
        # ---- errors: guards and targets
        "guard.name": "every [[guards]] entry needs a non-empty 'name'.",
        "guard.type": "guard '{name}': unknown type {value!r}. Use one of: {allowed}.",
        "guard.tool_stage": "tool stage is planned for a later release",
        "guard.stage": "guard '{name}': stage must be 'input' or 'output', got {value!r}.",
        "guard.unknown_options": "guard '{name}': unknown option(s) {unknown} for type '{type}'.",
        "guard.callable": "guard '{name}': 'callable' = \"module:function\" is required.",
        "guard.replay_path": "guard '{name}': 'path' to the recorded .jsonl is required.",
        "guard.callable_form": "{what}: callable must look like 'module:function', got {ref!r}.",
        "guard.import": "{what}: cannot import module '{module}' ({detail}). Put it next to the config file or "
                        "install it.",
        "guard.no_callable": "{what}: '{module}' has no callable named '{function}'.",
        "guard.mode": "mode must be 'strict' or 'loose', got {value!r}.",
        "guard.mode_named": "guard '{name}': mode must be 'strict' or 'loose', got {value!r}.",
        "guard.missing_extra": "the 'hf-qwen3guard' guard needs {packages}, which is not installed. Install the "
                               "extra with `uv sync --extra hf` (in a clone) or `pip install \"guarddiff[hf]\"`.",
        "guard.regex_patterns": "guard '{name}': 'patterns' must be a non-empty list of regular expressions.",
        "guard.regex_invalid": "guard '{name}': invalid regex {pattern!r} ({detail}).",
        "guard.replay_mode": "guard '{name}': set mode = \"strict\" | \"loose\" or block_labels = [...].",
        "guard.replay_missing": "replay file not found: {path}. Set 'path' to a recorded .jsonl file.",
        "guard.replay_record": "{path}:{lineno}: invalid replay record ({kind}). Each line needs at least "
                               "{example}.",
        "target.type": "[target] unknown type {value!r}. Use one of: {allowed}.",
        "target.unknown_options": "[target] unknown option(s) {unknown} for type '{type}'.",
        "target.callable": "[target] type='python' needs callable = \"module:function\".",
        "target.openai_model": "[target] type='openai' needs 'model' (for example model = \"qwen3:4b\").",
        "target.openai_url": "[target] base_url must start with http:// or https://, got {value!r}.",
        "target.mock_regex": "[target] self_refuse has an invalid regex ({detail}).",
        "judge.regex": "[judge] invalid refusal regex {pattern!r} ({detail}).",
    },
    "ko": {
        # ---- command line: help text
        "cli.description": "같은 프롬프트로 가드레일을 끈 경우와 켠 경우를 비교합니다.",
        "cli.lang_help": "출력 언어: en 또는 ko (기본값: GUARDDIFF_LANG, 다음 LC_ALL / LC_MESSAGES / LANG, "
                         "모두 없으면 en)",
        "help.run": "TOML 설정으로 비교 실행을 수행합니다",
        "help.report": "출력 폴더에서 보고서를 다시 만듭니다",
        "help.gate": "변형이 한도를 넘으면 종료 코드 1로 끝납니다 (CI용)",
        "help.demo": "오프라인 예제를 복사해 실행합니다 (연습용 목 모드, 네트워크 없음)",
        "help.init": "수정해서 쓸 예제 설정과 프롬프트를 복사합니다",
        "help.run.config": "guarddiff TOML 설정 파일 경로",
        "help.run.out": "출력 폴더 (기본값: guarddiff-out)",
        "help.run.latency": "설정의 [run].latency 를 덮어씁니다",
        "help.run.fresh": "이전 결과를 재사용하지 않고 선택한 변형의 모든 쌍을 다시 실행합니다",
        "help.run.only": "이 변형들만 실행합니다 (기준 변형 포함). 나머지 변형의 결과는 그대로 보존됩니다",
        "help.run.concurrency": "(항목, 변형) 쌍 N개를 동시에 실행합니다 (기본값 1 = 하나씩 차례로)",
        "help.report.dir": "`run` 이 만든 출력 폴더",
        "help.report.format": "보고서 형식 (기본값: html)",
        "help.gate.summary": "`run` 이 만든 summary.json",
        "help.gate.variant": "점검할 변형",
        "help.gate.max_overblock": "가드가 막은 정상 프롬프트 비율이 X보다 높으면 실패합니다",
        "help.gate.min_asr_reduction": "기준 변형 대비 ASR 감소폭이 X보다 작으면 실패합니다",
        "help.gate.max_p95_ms": "가드의 p95 지연(ms)이 X보다 크면 실패합니다",
        "help.gate.max_indeterminate": "실패한 항목의 비율이 X보다 높으면 실패합니다 (기본값: 0)",
        "help.gate.max_cost_usd": "가드 총비용(USD)이 X보다 크면 실패합니다",
        "help.gate.allow_indeterminate": "가드·대상 실패를 이유로 실패 처리하지 않습니다 (기본값: 판정 불가 항목이 "
                                         "하나라도 있으면 게이트 실패. 일부 비율만 허용하려면 --max-indeterminate X "
                                         "사용). --max-indeterminate 와 함께 쓸 수 없습니다",
        "help.demo.out": "예제를 복사할 폴더 (기본값: guarddiff-demo)",
        "help.init.dir": "파일을 쓸 폴더 (기본값: 현재 폴더)",
        "help.init.force": "기존 파일을 덮어씁니다",
        "cli.error_prefix": "오류",
        # ---- command line: output
        "run.baseline_line": "기준={baseline}  쌍={pairs}  파일에서 재사용={resumed}",
        "run.rerun": "{n}개 쌍을 다시 실행했습니다 (설정이 바뀜)",
        "run.retry": "판정 불가였던 {n}개 쌍을 다시 실행했습니다 (지난번에 실패함)",
        "run.kept": "이번에 실행하지 않은 변형의 {n}개 쌍을 보존했습니다: {variants}",
        "run.paths": "결과:   {results}\n요약:   {summary}\n보고서: {report}",
        "run.warn_concurrency": "경고: 측정 지연 모드에서 --concurrency > 1 을 쓰면 호출이 겹쳐 측정 지연이 "
                                "부풀려질 수 있습니다. 가드를 비교하려면 시뮬레이션 지연을 사용하십시오.\n",
        "gate.failed": "변형 {variant!r} 이(가) 게이트에서 실패했습니다:",
        "gate.passed": "변형 {variant!r} 이(가) 게이트를 통과했습니다",
        "gate.note_allowed": "참고: 판정 불가 비율 {rate} 은(는) 지정한 옵션에 따라 허용되었습니다. 실패한 항목은 "
                             "놓친 공격으로 계산되지 않습니다.",
        "gate.need_limit": "한도를 하나 이상 지정하십시오: {options}.",
        "gate.exclusive": "--allow-indeterminate 와 --max-indeterminate 는 함께 쓸 수 없습니다. 실패 항목의 일부 "
                          "비율만 허용하려면 --max-indeterminate X 를, 점검을 끄려면 --allow-indeterminate 를 "
                          "지정하십시오.",
        "init.wrote": "작성했습니다: {path}",
        "init.next": "guarddiff.toml 과 items.jsonl 을 수정한 뒤 `guarddiff run guarddiff.toml --out out` 을 "
                     "실행하십시오.",
        "init.exists": "{paths} 이(가) 이미 있습니다. 덮어쓰려면 --force 를 지정하거나 다른 폴더를 선택하십시오.",
        "arg.concurrency_type": "1 이상의 정수여야 합니다. 받은 값: {value!r}",
        "arg.concurrency_min": "1 이상이어야 합니다 (1 = 한 번에 한 쌍). 받은 값: {value}",
        # ---- table / report headings
        "table.variant": "variant",
        "report.title": "guarddiff 보고서",
        "report.summary": "요약",
        "report.per_item": "항목별 결과",
        "report.notice_mock": "연습용 목(mock) 대상입니다 (실제 LLM 이 아닙니다)",
        "report.notice_simulated": "시뮬레이션 지연입니다 (재현 가능한 자리표시 값이며 측정값이 아닙니다)",
        "report.asr_reduction_the": "ASR 감소폭",
        "report.warn_indeterminate": "판정 불가 항목(가드 또는 대상이 실패함)이 있는 변형: {variants}. 이 항목은 "
                                     "놓친 공격으로 계산되지 않으므로 {reduction} 이(가) 실제보다 좋아 보일 수 "
                                     "있습니다. 실패 원인을 고치거나 `guarddiff gate` 를 실행하십시오.",
        "md.variant": "변형",
        "md.asr": "ASR (95% CI)",
        "md.asr_reduction": "ASR 감소폭",
        "md.overblock": "과차단 (95% CI)",
        "md.indeterminate": "판정 불가",
        "md.p50": "p50 ms",
        "md.p95": "p95 ms",
        "md.cost": "비용 USD",
        "md.mcnemar": "McNemar p",
        "md.baseline": "기준 변형: `{baseline}`. 비율의 분모는 해당 라벨의 전체 항목입니다.",
        "html.baseline": "기준: <b>{baseline}</b>. 비율의 분모는 해당 라벨의 전체 항목입니다(판정 불가 포함). "
                         "구간은 Wilson 95% 이고, 짝지은 p 값은 정확 McNemar 검정입니다.",
        "html.variant": "변형",
        "html.n": "n 공격 / 정상",
        "html.asr": "ASR",
        "html.asr_ci": "ASR 95% CI",
        "html.asr_reduction": "ASR 감소폭",
        "html.overblock": "과차단",
        "html.overblock_ci": "과차단 95% CI",
        "html.total_overrefusal": "전체 과잉 거절",
        "html.indeterminate": "판정 불가",
        "html.latency": "지연 p50 / p95 ms",
        "html.cost": "비용 USD",
        "html.calls": "대상 호출 수",
        "html.fixed": "개선 / 악화",
        "html.mcnemar": "McNemar p",
        "html.redundant": "중복 차단",
        "html.id": "id",
        "html.label": "라벨",
        "html.prompt": "프롬프트",
        "html.outcomes": "결과 종류: {outcomes}.",
        # ---- errors: config
        "config.not_found": "설정 파일을 찾을 수 없습니다: {path}. `guarddiff init` 으로 만들거나 올바른 경로를 "
                            "지정하십시오.",
        "config.bad_toml": "{path}: TOML 형식이 올바르지 않습니다 ({detail}).",
        "config.not_utf8": "{path}: 파일은 UTF-8 텍스트여야 합니다 ({detail}).",
        "config.unknown_top": "{where}: 알 수 없는 최상위 키 {unknown} 가 있습니다. 허용되는 키: {allowed}.",
        "config.run_keys": "{where}: [run] 에는 {allowed} 만 쓸 수 있습니다.",
        "config.items_required": "{where}: [run].items 가 필요합니다. 예: items = \"items.jsonl\".",
        "config.latency": "{where}: [run].latency 는 'simulated' 또는 'measured' 여야 합니다. 받은 값: {value!r}.",
        "config.guards_tables": "{where}: guards 는 [[guards]] 테이블로 작성해야 합니다.",
        "config.dup_guards": "{where}: 가드 이름 {names} 이(가) 중복되었습니다. 이름은 고유해야 합니다.",
        "config.no_variants": "{where}: [[variants]] 테이블(name + guards 목록)을 하나 이상 추가하십시오. 예: "
                              "name = \"none\", guards = [].",
        "config.variant_name": "{where}: 모든 [[variants]] 항목에는 'name' 이 필요합니다.",
        "config.variant_guards": "{where}: 변형 '{variant}': guards 는 가드 이름의 목록이어야 합니다.",
        "config.variant_unknown_guard": "{where}: 변형 '{variant}' 이(가) 정의되지 않은 가드 {missing} 를 사용합니다. "
                                        "정의된 가드: {defined}.",
        "config.dup_variants": "{where}: {names} 에 변형 이름이 중복되었습니다.",
        "config.baseline": "{where}: [run].baseline {value!r} 은(는) 변형 {names} 중 하나가 아닙니다.",
        "config.tables": "{where}: [target] 과 [judge] 는 테이블이어야 합니다.",
        "config.judge_type": "{where}: [judge].type {value!r} 은(는) 아직 지원하지 않습니다. 'rules' 를 "
                             "사용하십시오.",
        # ---- errors: items
        "items.not_found": "항목 파일을 찾을 수 없습니다: {path}. 설정의 [run].items 를 존재하는 .jsonl 파일로 "
                           "지정하십시오.",
        "items.bad_json": "{where}: JSON 형식이 올바르지 않습니다 ({detail}). 각 줄은 JSON 객체 하나여야 합니다.",
        "items.not_object": "{where}: JSON 객체가 필요하지만 {type} 을(를) 받았습니다.",
        "items.field": "{where}: '{key}' 필드는 필수이며 비어 있지 않은 문자열이어야 합니다.",
        "items.label": "{where}: label 은 'attack' 또는 'benign' 이어야 합니다. 받은 값: {value!r}.",
        "items.dup_id": "{where}: id {value!r} 이(가) 중복되었습니다. id 는 고유해야 합니다.",
        "items.empty": "{path} 에 항목이 없습니다. {example} 같은 줄을 하나 이상 추가하십시오.",
        # ---- errors: gate
        "gate.summary_not_found": "요약 파일을 찾을 수 없습니다: {path}. `guarddiff run CONFIG --out DIR` 을 실행한 "
                                  "뒤 DIR/summary.json 을 지정하십시오.",
        "gate.summary_bad_json": "{path}: 올바른 JSON 이 아닙니다 ({detail}). `guarddiff run` 이 만든 summary.json 을 "
                                 "지정하십시오.",
        "gate.summary_not_object": "{path}: JSON 객체가 필요합니다.",
        "gate.unknown_variant": "변형 {variant!r} 이(가) 요약에 없습니다. 사용 가능: {available}.",
        "gate.unknown_limit": "알 수 없는 게이트 한도 {name!r} 입니다. 사용 가능: {allowed}.",
        "gate.bad_limit": "{name} 은(는) 0 이상의 숫자여야 합니다. 받은 값: {value!r}.",
        "gate.no_metric": "이 요약에는 변형 {variant!r} 의 {key} 값이 없습니다.",
        # ---- errors: runner
        "runner.only_unknown": "--only: 알 수 없는 변형 {unknown} 입니다. 정의된 변형: {names}.",
        "runner.concurrency": "concurrency 는 1 이상의 정수여야 합니다 (1 = 한 번에 한 쌍). 받은 값: {value!r}.",
        "runner.latency": "latency 는 'simulated' 또는 'measured' 여야 합니다. 받은 값: {value!r}.",
        "runner.no_results": "{path} 을(를) 찾을 수 없습니다. 먼저 `guarddiff run CONFIG --out {out}` 을 "
                             "실행하십시오.",
        "runner.no_rows": "{path} 에 읽을 수 있는 행이 없습니다. --fresh 로 다시 실행하십시오.",
        # ---- errors: guards and targets
        "guard.name": "모든 [[guards]] 항목에는 비어 있지 않은 'name' 이 필요합니다.",
        "guard.type": "가드 '{name}': 알 수 없는 type {value!r} 입니다. 사용 가능: {allowed}.",
        "guard.tool_stage": "tool 단계는 이후 릴리스에서 제공할 예정입니다",
        "guard.stage": "가드 '{name}': stage 는 'input' 또는 'output' 이어야 합니다. 받은 값: {value!r}.",
        "guard.unknown_options": "가드 '{name}': type '{type}' 에서 알 수 없는 옵션 {unknown} 입니다.",
        "guard.callable": "가드 '{name}': 'callable' = \"module:function\" 이 필요합니다.",
        "guard.replay_path": "가드 '{name}': 녹화된 .jsonl 의 'path' 가 필요합니다.",
        "guard.callable_form": "{what}: callable 은 'module:function' 형태여야 합니다. 받은 값: {ref!r}.",
        "guard.import": "{what}: 모듈 '{module}' 을(를) 가져올 수 없습니다 ({detail}). 설정 파일 옆에 두거나 "
                        "설치하십시오.",
        "guard.no_callable": "{what}: '{module}' 에 '{function}' 이라는 호출 가능 객체가 없습니다.",
        "guard.mode": "mode 는 'strict' 또는 'loose' 여야 합니다. 받은 값: {value!r}.",
        "guard.mode_named": "가드 '{name}': mode 는 'strict' 또는 'loose' 여야 합니다. 받은 값: {value!r}.",
        "guard.missing_extra": "'hf-qwen3guard' 가드에는 {packages} 이(가) 필요하지만 설치되어 있지 않습니다. "
                               "`uv sync --extra hf` (클론한 경우) 또는 `pip install \"guarddiff[hf]\"` 로 추가 "
                               "패키지를 설치하십시오.",
        "guard.regex_patterns": "가드 '{name}': 'patterns' 는 비어 있지 않은 정규식 목록이어야 합니다.",
        "guard.regex_invalid": "가드 '{name}': 올바르지 않은 정규식 {pattern!r} ({detail}).",
        "guard.replay_mode": "가드 '{name}': mode = \"strict\" | \"loose\" 또는 block_labels = [...] 를 지정하십시오.",
        "guard.replay_missing": "재생 파일을 찾을 수 없습니다: {path}. 'path' 를 녹화된 .jsonl 파일로 지정하십시오.",
        "guard.replay_record": "{path}:{lineno}: 재생 기록이 올바르지 않습니다 ({kind}). 각 줄에는 최소한 {example} "
                               "가 있어야 합니다.",
        "target.type": "[target] 알 수 없는 type {value!r} 입니다. 사용 가능: {allowed}.",
        "target.unknown_options": "[target] type '{type}' 에서 알 수 없는 옵션 {unknown} 입니다.",
        "target.callable": "[target] type='python' 에는 callable = \"module:function\" 이 필요합니다.",
        "target.openai_model": "[target] type='openai' 에는 'model' 이 필요합니다 (예: model = \"qwen3:4b\").",
        "target.openai_url": "[target] base_url 은 http:// 또는 https:// 로 시작해야 합니다. 받은 값: {value!r}.",
        "target.mock_regex": "[target] self_refuse 에 올바르지 않은 정규식이 있습니다 ({detail}).",
        "judge.regex": "[judge] 올바르지 않은 거절 정규식 {pattern!r} ({detail}).",
    },
}
