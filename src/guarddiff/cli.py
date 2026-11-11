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
from .report.html import write_html
from .report.markdown import indeterminate_warning, notices, reduction_text, render_markdown
from .runner import RunResult, load_run, run_ablation

EXAMPLE_FILES = ("guarddiff.toml", "items.jsonl")


def _table(result: RunResult) -> str:
    lines = [f"{'variant':10} {'ASR':>6} {'ASR 95% CI':>13} {'dASR':>7} {'overblk':>8} {'over-all':>8} "
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
    print(f"baseline={result.baseline}  pairs={total}  resumed_from_file={skipped}")
    changed = result.meta.get("config_changed_pairs", 0)
    if changed:
        print(f"rerun {changed} pairs (config changed)")
    retried = result.meta.get("retried_indeterminate_pairs", 0)
    if retried:  # pairs that failed last time are never reused, so fixing the cause and running again is enough
        print(f"retry {retried} indeterminate pairs (they failed last time)")
    kept = result.meta.get("kept_other_pairs", 0)
    if kept:  # --only: the other variants' rows stay in results.jsonl for the next full run
        print(f"kept {kept} pairs of variants not run this time: {', '.join(result.meta['kept_other_variants'])}")
    if result.out_dir is not None:
        print(f"results: {result.out_dir / 'results.jsonl'}\nsummary: {result.out_dir / 'summary.json'}\n"
              f"report:  {result.out_dir / 'report.html'}")


def _example_dir() -> Path:
    return Path(str(resources.files("guarddiff").joinpath("examples", "offline")))


def _copy_example(dest: Path, *, overwrite: bool) -> list[Path]:
    src = _example_dir()
    targets = [dest / name for name in EXAMPLE_FILES]
    clash = [t for t in targets if t.exists()]
    if clash and not overwrite:
        raise ConfigError(f"{', '.join(str(c) for c in clash)} already exist(s). "
                          "Pass --force to overwrite, or choose another folder.")
    dest.mkdir(parents=True, exist_ok=True)
    for name, t in zip(EXAMPLE_FILES, targets):
        shutil.copyfile(src / name, t)
    return targets


def _concurrency(text: str) -> int:
    """argparse type: a whole number >= 1."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a whole number >= 1, got {text!r}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1 (1 = one pair at a time), got {value}")
    return value


def cmd_run(args: argparse.Namespace) -> int:
    result = run_ablation(args.config, args.out, latency=args.latency, fresh=args.fresh, only=args.only,
                          concurrency=args.concurrency)
    if args.concurrency > 1 and result.meta.get("latency_mode") == "measured":
        # one whole line in one write: lines never interleave
        sys.stderr.write("warning: --concurrency > 1 with measured latency: calls overlap, so measured "
                         "latencies can be inflated. Use simulated latency to compare guards.\n")
    _print_result(result)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    result = load_run(args.dir)
    if args.format == "md":
        sys.stdout.write(render_markdown(result))
    elif args.format == "json":
        import json  # noqa: PLC0415

        print(json.dumps({"variants": result.variants, "baseline": result.baseline, "summary": result.summary},
                         ensure_ascii=False, indent=2))
    else:
        print(write_html(result, Path(args.dir) / "report.html"))
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    limits = {name: getattr(args, name) for name in LIMITS}
    if all(v is None for v in limits.values()):
        raise ConfigError("give at least one limit: " + ", ".join("--" + n.replace("_", "-") for n in LIMITS) + ".")
    if args.allow_indeterminate and args.max_indeterminate is not None:
        # one says "allow any share of failed items", the other "allow at most X": refuse to guess which one wins
        raise ConfigError("--allow-indeterminate and --max-indeterminate cannot be used together. Give "
                          "--max-indeterminate X to allow a share of failed items, or --allow-indeterminate "
                          "to switch the check off.")
    given = {name: value for name, value in limits.items() if value is not None}
    if args.allow_indeterminate:
        given["max_indeterminate"] = None  # explicit opt-out of the default "no failed items" rule
    summary = load_summary(args.summary)
    failures = check_gate(summary, args.variant, **given)  # unset max_indeterminate -> library default (0)
    if failures:
        print(f"gate FAILED for variant {args.variant!r}:")
        for f in failures:
            print(f"  {f}")
        return 1
    print(f"gate passed for variant {args.variant!r}")
    per_variant = summary["summary"] if isinstance(summary.get("summary"), dict) else summary
    rate = per_variant[args.variant].get("indeterminate_rate") or 0
    if rate > 0:  # passed only because failed items were allowed; say so rather than look like a clean pass
        print(f"note: indeterminate_rate {rate} was allowed by the options given. Failed items are not counted "
              "as missed attacks.")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    dest = Path(args.out)
    _copy_example(dest, overwrite=True)
    result = run_ablation(dest / "guarddiff.toml", dest / "out", latency="simulated", fresh=True)
    _print_result(result)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    for t in _copy_example(Path(args.dir), overwrite=args.force):
        print(f"wrote {t}")
    print("Edit guarddiff.toml and items.jsonl, then run `guarddiff run guarddiff.toml --out out`.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="guarddiff", description="Compare guardrails off vs on with the same prompts.")
    p.add_argument("--version", action="version", version=f"guarddiff {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="{run,report,gate,demo,init}")

    r = sub.add_parser("run", help="run the ablation from a TOML config")
    r.add_argument("config")
    r.add_argument("--out", default="guarddiff-out", help="output folder (default: guarddiff-out)")
    r.add_argument("--latency", choices=("simulated", "measured"), default=None,
                   help="override [run].latency from the config")
    r.add_argument("--fresh", action="store_true",
                   help="do not reuse earlier results; run every pair of the selected variants again")
    r.add_argument("--only", nargs="+", metavar="VARIANT",
                   help="run only these variants (plus the baseline); results of the other variants are kept")
    r.add_argument("--concurrency", type=_concurrency, default=1, metavar="N",
                   help="run N (item, variant) pairs at the same time (default 1 = one after another)")
    r.set_defaults(func=cmd_run)

    rp = sub.add_parser("report", help="rebuild a report from an output folder")
    rp.add_argument("dir")
    rp.add_argument("--format", choices=("html", "md", "json"), default="html")
    rp.set_defaults(func=cmd_report)

    g = sub.add_parser("gate", help="exit 1 when a variant breaks a limit (for CI)")
    g.add_argument("summary", help="summary.json written by `run`")
    g.add_argument("--variant", required=True)
    for name in LIMITS:
        g.add_argument("--" + name.replace("_", "-"), dest=name, type=float, default=None)
    g.add_argument("--allow-indeterminate", action="store_true",
                   help="do not fail on guard/target failures (default: any indeterminate item fails the gate; "
                        "use --max-indeterminate X to allow a share). Cannot be combined with --max-indeterminate")
    g.set_defaults(func=cmd_gate)

    d = sub.add_parser("demo", help="copy the offline example and run it (practice mock, no network)")
    d.add_argument("--out", default="guarddiff-demo")
    d.set_defaults(func=cmd_demo)

    i = sub.add_parser("init", help="copy the example config and prompts to edit")
    i.add_argument("dir", nargs="?", default=".")
    i.add_argument("--force", action="store_true")
    i.set_defaults(func=cmd_init)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except GuarddiffError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
