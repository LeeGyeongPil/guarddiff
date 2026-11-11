"""Markdown summary (one table row per variant), meant for CI step summaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..runner import RunResult


def notices(result: "RunResult") -> list[str]:
    """Honesty notes shown above every report: mock target, simulated latency."""
    notes: list[str] = []
    if result.meta.get("target_type", "mock") == "mock":
        notes.append("practice mock target (not a real LLM)")
    if any(s.get("latency_source") in ("simulated", "mixed") for s in result.summary.values()):
        notes.append("simulated latency (reproducible placeholder values, not measurements)")
    return notes


def reduction_text(summary: dict, digits: int) -> str:
    """ASR reduction for a table cell. A trailing '!' means the variant has indeterminate items:
    failed items are not counted as missed attacks, so the reduction may look better than it is."""
    red = summary["asr_reduction_vs_none"]
    if red is None:
        return "-"
    text = f"{red:.{digits}f}"
    return text + "!" if summary["indeterminate_rate"] > 0 else text


def indeterminate_warning(result: "RunResult", reduction_name: str) -> str | None:
    """One warning line when any variant has indeterminate items (used by `run`, Markdown and HTML)."""
    flagged = [v for v in result.variants if result.summary[v]["indeterminate_rate"] > 0]
    if not flagged:
        return None
    return (f"indeterminate items (a guard or the target failed) in: {', '.join(flagged)}. They are not counted "
            f"as missed attacks, so {reduction_name} may look better than it is. Fix the failures, "
            "or run `guarddiff gate`.")


def _ci(c: list[float]) -> str:
    return f"{c[0]:.2f}-{c[1]:.2f}"


def render_markdown(result: "RunResult") -> str:
    lines = ["## guarddiff report", ""]
    for n in notices(result):
        lines.append(f"> {n}")
    if lines[-1] != "":
        lines.append("")
    lines += ["| variant | ASR (95% CI) | ASR reduction | overblock (95% CI) | indeterminate | p50 ms | p95 ms "
              "| cost USD | McNemar p |",
              "|---|---|---|---|---|---|---|---|---|"]
    for v in result.variants:
        s = result.summary[v]
        pair = s["paired_vs_none"]
        lines.append(
            f"| {v} | {s['asr']:.3f} ({_ci(s['asr_ci95'])}) | {reduction_text(s, 4)} "
            f"| {s['guard_overblock_rate']:.3f} ({_ci(s['guard_overblock_ci95'])}) "
            f"| {s['indeterminate_rate']:.3f} | {s['guard_latency_ms_p50']:.1f} | {s['guard_latency_ms_p95']:.1f} "
            f"| {s['guard_cost_usd_total']:.4f} | {'-' if pair is None else pair['mcnemar_p']} |")
    warning = indeterminate_warning(result, "the ASR reduction")
    if warning:
        lines += ["", f"> **!** {warning}"]  # same warning as the `run` table, so a CI summary shows it too
    lines += ["", f"Baseline variant: `{result.baseline}`. Rates use all items of a label as the denominator."]
    return "\n".join(lines) + "\n"
