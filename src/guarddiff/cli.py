"""Command line: run | report | gate | demo | init. Exit codes: 0 ok, 1 gate failed, 2 usage or config error."""

from __future__ import annotations

import argparse
import shutil
import sys
from importlib import resources
from pathlib import Path
from typing import Sequence

from . import __version__
from .errors import ConfigError, GuarddiffError
from .gate import LIMITS, check_gate, load_summary
from .i18n import LANGS, resolve_lang, scan_lang_option, t, use_lang
from .report.html import write_html
from .report.markdown import indeterminate_warning, notices, reduction_text, render_markdown
from .runner import RunResult, load_run, run_ablation

EXAMPLE_FILES = ("guarddiff.toml", "items.jsonl")


def _table(result: RunResult) -> str:
    # Column heads are metric names (ASR, dASR, McNemar p ...) and stay English in every language: the table is
    # fixed-width and Korean characters are two columns wide.
    lines = [f"{t('table.variant'):10} {'ASR':>6} {'ASR 95% CI':>13} {'dASR':>7} {'overblk':>8} {'over-all':>8} "
             f"{'indet':>6} {'p50ms':>8} {'p95ms':>8} {'cost$':>8} {'McNemar p':>9}"]
    for v in result.variants:
        s = result.summary[v]
        pair = s["paired_vs_none"]
        lo, hi = s["asr_ci95"]
        red_txt = reduction_text(s, 3)  # ends in "!" when failed items make the reduction look too good
        p_txt = "-" if pair is None else f"{pair['mcnemar_p']:.4f}"
        ci_txt = f"{lo:.2f}-{hi:.2f}"
        lines.append(
            f"{v:10} {s['asr']:6.3f} {ci_txt:>13} {red_txt:>7} "
            f"{s['guard_overblock_rate']:8.3f} {s['total_overrefusal_rate']:8.3f} {s['indeterminate_rate']:6.3f} "
            f"{s['guard_latency_ms_p50']:8.2f} {s['guard_latency_ms_p95']:8.2f} {s['guard_cost_usd_total']:8.4f} "
            f"{p_txt:>9}")
    return "\n".join(lines)


def _print_result(result: RunResult) -> None:
    for n in notices(result):
        print(f"[{n}]")
    print(_table(result))
    warning = indeterminate_warning(result, "dASR")
    if warning:
        print(f"! {warning}")
    skipped = result.meta.get("skipped_pairs", 0)
    total = len(result.rows)
    print(t("run.baseline_line", baseline=result.baseline, pairs=total, resumed=skipped))
    changed = result.meta.get("config_changed_pairs", 0)
    if changed:
        print(t("run.rerun", n=changed))
    retried = result.meta.get("retried_indeterminate_pairs", 0)
    if retried:  # pairs that failed last time are never reused, so fixing the cause and running again is enough
        print(t("run.retry", n=retried))
    kept = result.meta.get("kept_other_pairs", 0)
    if kept:  # --only: the other variants' rows stay in results.jsonl for the next full run
        print(t("run.kept", n=kept, variants=", ".join(result.meta["kept_other_variants"])))
    if result.out_dir is not None:
        print(t("run.paths", results=result.out_dir / "results.jsonl", summary=result.out_dir / "summary.json",
                report=result.out_dir / "report.html"))


def _example_dir() -> Path:
    return Path(str(resources.files("guarddiff").joinpath("examples", "offline")))


def _copy_example(dest: Path, *, overwrite: bool) -> list[Path]:
    src = _example_dir()
    targets = [dest / name for name in EXAMPLE_FILES]
    clash = [t_ for t_ in targets if t_.exists()]
    if clash and not overwrite:
        raise ConfigError(t("init.exists", paths=", ".join(str(c) for c in clash)))
    dest.mkdir(parents=True, exist_ok=True)
    for name, target in zip(EXAMPLE_FILES, targets):
        shutil.copyfile(src / name, target)
    return targets


def _concurrency(text: str) -> int:
    """argparse type: a whole number >= 1."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(t("arg.concurrency_type", value=text)) from None
    if value < 1:
        raise argparse.ArgumentTypeError(t("arg.concurrency_min", value=value))
    return value


def cmd_run(args: argparse.Namespace) -> int:
    result = run_ablation(args.config, args.out, latency=args.latency, fresh=args.fresh, only=args.only,
                          concurrency=args.concurrency)
    if args.concurrency > 1 and result.meta.get("latency_mode") == "measured":
        # one whole line in one write: lines never interleave
        sys.stderr.write(t("run.warn_concurrency"))
    _print_result(result)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    result = load_run(args.dir)
    if args.format == "md":
        sys.stdout.write(render_markdown(result))
    elif args.format == "json":
        import json  # noqa: PLC0415

        # machine-readable: identical in every language
        print(json.dumps({"variants": result.variants, "baseline": result.baseline, "summary": result.summary},
                         ensure_ascii=False, indent=2))
    else:
        print(write_html(result, Path(args.dir) / "report.html"))
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    limits = {name: getattr(args, name) for name in LIMITS}
    if all(v is None for v in limits.values()):
        raise ConfigError(t("gate.need_limit", options=", ".join("--" + n.replace("_", "-") for n in LIMITS)))
    if args.allow_indeterminate and args.max_indeterminate is not None:
        # one says "allow any share of failed items", the other "allow at most X": refuse to guess which one wins
        raise ConfigError(t("gate.exclusive"))
    given = {name: value for name, value in limits.items() if value is not None}
    if args.allow_indeterminate:
        given["max_indeterminate"] = None  # explicit opt-out of the default "no failed items" rule
    summary = load_summary(args.summary)
    failures = check_gate(summary, args.variant, **given)  # unset max_indeterminate -> library default (0)
    if failures:
        print(t("gate.failed", variant=args.variant))
        for f in failures:
            print(f"  {f}")
        return 1
    print(t("gate.passed", variant=args.variant))
    per_variant = summary["summary"] if isinstance(summary.get("summary"), dict) else summary
    rate = per_variant[args.variant].get("indeterminate_rate") or 0
    if rate > 0:  # passed only because failed items were allowed; say so rather than look like a clean pass
        print(t("gate.note_allowed", rate=rate))
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    dest = Path(args.out)
    _copy_example(dest, overwrite=True)
    result = run_ablation(dest / "guarddiff.toml", dest / "out", latency="simulated", fresh=True)
    _print_result(result)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    for written in _copy_example(Path(args.dir), overwrite=args.force):
        print(t("init.wrote", path=written))
    print(t("init.next"))
    return 0


def _lang_parent() -> argparse.ArgumentParser:
    """``--lang`` is accepted before and after the sub-command. default=SUPPRESS keeps an absent option from
    overwriting an earlier one. `main` has already read the value from argv; this only declares it."""
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--lang", choices=LANGS, default=argparse.SUPPRESS, help=t("cli.lang_help"))
    return parent


def build_parser() -> argparse.ArgumentParser:
    lang = _lang_parent()
    p = argparse.ArgumentParser(prog="guarddiff", description=t("cli.description"), parents=[lang])
    p.add_argument("--version", action="version", version=f"guarddiff {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="{run,report,gate,demo,init}")

    r = sub.add_parser("run", help=t("help.run"), parents=[lang])
    r.add_argument("config", help=t("help.run.config"))
    r.add_argument("--out", default="guarddiff-out", help=t("help.run.out"))
    r.add_argument("--latency", choices=("simulated", "measured"), default=None, help=t("help.run.latency"))
    r.add_argument("--fresh", action="store_true", help=t("help.run.fresh"))
    r.add_argument("--only", nargs="+", metavar="VARIANT", help=t("help.run.only"))
    r.add_argument("--concurrency", type=_concurrency, default=1, metavar="N", help=t("help.run.concurrency"))
    r.set_defaults(func=cmd_run)

    rp = sub.add_parser("report", help=t("help.report"), parents=[lang])
    rp.add_argument("dir", help=t("help.report.dir"))
    rp.add_argument("--format", choices=("html", "md", "json"), default="html", help=t("help.report.format"))
    rp.set_defaults(func=cmd_report)

    g = sub.add_parser("gate", help=t("help.gate"), parents=[lang])
    g.add_argument("summary", help=t("help.gate.summary"))
    g.add_argument("--variant", required=True, help=t("help.gate.variant"))
    for name in LIMITS:
        g.add_argument("--" + name.replace("_", "-"), dest=name, type=float, default=None, metavar="X",
                       help=t("help.gate." + name))
    g.add_argument("--allow-indeterminate", action="store_true", help=t("help.gate.allow_indeterminate"))
    g.set_defaults(func=cmd_gate)

    d = sub.add_parser("demo", help=t("help.demo"), parents=[lang])
    d.add_argument("--out", default="guarddiff-demo", help=t("help.demo.out"))
    d.set_defaults(func=cmd_demo)

    i = sub.add_parser("init", help=t("help.init"), parents=[lang])
    i.add_argument("dir", nargs="?", default=".", help=t("help.init.dir"))
    i.add_argument("--force", action="store_true", help=t("help.init.force"))
    i.set_defaults(func=cmd_init)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    # The language must be known before the parser is built (help text is made then), so read --lang first.
    # A bad value is left for argparse to reject with its own "invalid choice" error.
    with use_lang(resolve_lang(scan_lang_option(args_list))):
        args = build_parser().parse_args(args_list)
        try:
            return int(args.func(args))
        except GuarddiffError as e:
            print(f"{t('cli.error_prefix')}: {e}", file=sys.stderr)
            return 2
