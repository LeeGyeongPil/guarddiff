"""Single-file HTML report. Every dynamic value is escaped; no external resources are referenced."""

from __future__ import annotations

from html import escape
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING

from ..i18n import current_lang, t
from ..outcomes import OUTCOMES
from .markdown import indeterminate_warning, notices, reduction_text

if TYPE_CHECKING:
    from ..runner import RunResult

_PAGE = Template("""<!doctype html>
<html lang="$lang"><head><meta charset="utf-8"><title>$title</title>
<style>
body{font-family:system-ui,sans-serif;margin:1.5rem;color:#222}
table{border-collapse:collapse;margin:1rem 0;font-size:.9rem}
th,td{border:1px solid #ccc;padding:.3rem .6rem;text-align:left;vertical-align:top}
th{background:#f3f3f3}.note{background:#fff6d6;border:1px solid #e0c870;padding:.4rem .8rem;margin:.3rem 0}
.o-blocked,.o-model_refused,.o-passed{background:#e6f4e6}.o-missed,.o-overblocked{background:#fbe3e3}
.o-model_overrefused{background:#fdf0d5}.o-indeterminate{background:#e3e3f4}
small{color:#555}
</style></head><body>
<h1>$title</h1>
$notes
<h2>$summary_heading</h2>
<p><small>$baseline_text</small></p>
$summary_table
<h2>$items_heading</h2>
$items_table
</body></html>
""")


def _e(x: object) -> str:
    return escape("" if x is None else str(x), quote=True)


def _ci(c: list[float]) -> str:
    return f"{c[0]:.4f}&ndash;{c[1]:.4f}"


def _summary_table(result: "RunResult") -> str:
    keys = ("variant", "n", "asr", "asr_ci", "asr_reduction", "overblock", "overblock_ci", "total_overrefusal",
            "indeterminate", "latency", "cost", "calls", "fixed", "mcnemar", "redundant")
    head = "<tr>" + "".join(f"<th>{_e(t('html.' + k))}</th>" for k in keys) + "</tr>"
    body = []
    for v in result.variants:
        s = result.summary[v]
        pair = s["paired_vs_none"]
        body.append(
            f"<tr><td>{_e(v)}</td><td>{s['n_attack']} / {s['n_benign']}</td><td>{s['asr']:.4f}</td>"
            f"<td>{_ci(s['asr_ci95'])}</td><td>{reduction_text(s, 4)}</td>"
            f"<td>{s['guard_overblock_rate']:.4f}</td><td>{_ci(s['guard_overblock_ci95'])}</td>"
            f"<td>{s['total_overrefusal_rate']:.4f}</td><td>{s['indeterminate_rate']:.4f}</td>"
            f"<td>{s['guard_latency_ms_p50']:.3f} / {s['guard_latency_ms_p95']:.3f}</td>"
            f"<td>{s['guard_cost_usd_total']:.4f}</td><td>{s['target_calls']}</td>"
            + ("<td>-</td><td>-</td><td>-</td>" if pair is None else
               f"<td>{pair['attack_fixed']} / {pair['attack_regressed']}</td><td>{pair['mcnemar_p']}</td>"
               f"<td>{pair['redundant_blocks']}</td>")
            + "</tr>")
    table = f"<table>{head}{''.join(body)}</table>"
    warning = indeterminate_warning(result, t("report.asr_reduction_the"))
    if warning:  # the '!' in the table points here
        table += f'<div class="note"><b>!</b> {_e(warning)}</div>'
    return table


def _items_table(result: "RunResult") -> str:
    order: list[str] = []
    for r in result.rows:
        if r.id not in order:
            order.append(r.id)
    first = {r.id: r for r in result.rows}
    cell = {(r.id, r.variant): r for r in result.rows}
    head = (f"<tr><th>{_e(t('html.id'))}</th><th>{_e(t('html.label'))}</th><th>{_e(t('html.prompt'))}</th>"
            + "".join(f"<th>{_e(v)}</th>" for v in result.variants) + "</tr>")
    body = []
    for i in order:
        f = first[i]
        tds = []
        for v in result.variants:
            r = cell.get((i, v))
            if r is None:
                tds.append("<td>-</td>")
                continue
            ev = f"<br><small>{_e(r.evidence)}</small>" if r.evidence else ""
            tds.append(f"<td class=\"o-{_e(r.outcome)}\"><b>{_e(r.outcome)}</b>{ev}</td>")
        body.append(f"<tr><td>{_e(i)}</td><td>{_e(f.label)}</td><td>{_e(f.prompt)}</td>{''.join(tds)}</tr>")
    legend = "<p><small>" + _e(t("html.outcomes", outcomes=", ".join(OUTCOMES))) + "</small></p>"
    return f"<table>{head}{''.join(body)}</table>{legend}"


def render_html(result: "RunResult") -> str:
    notes = "".join(f'<div class="note">{_e(n)}</div>' for n in notices(result))
    baseline_text = t("html.baseline", baseline=_e(result.baseline))  # the template holds the <b> tag; the name is escaped
    return _PAGE.substitute(lang=current_lang(), title=_e(t("report.title")), notes=notes,
                            summary_heading=_e(t("report.summary")), baseline_text=baseline_text,
                            summary_table=_summary_table(result), items_heading=_e(t("report.per_item")),
                            items_table=_items_table(result))


def write_html(result: "RunResult", path: str | Path) -> Path:
    p = Path(path)
    p.write_text(render_html(result), encoding="utf-8")
    return p
