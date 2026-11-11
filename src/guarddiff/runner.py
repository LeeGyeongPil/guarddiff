"""Run every item through every variant and keep results.jsonl up to date (resumable)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .config import Config, Variant, load_config
from .errors import ConfigError, GuarddiffError
from .guards import Guard, build_guard
from .items import Item, load_items
from .judges import RulesJudge
from .latency import MODES, simulated_latency
from .metrics import build_summary
from .outcomes import INDETERMINATE, ResultRow, classify
from .targets import Target, TargetReply, build_target

RESULTS_FILE = "results.jsonl"
SUMMARY_FILE = "summary.json"
SCHEMA_VERSION = 1


@dataclass
class RunResult:
    """What ``run_ablation`` returns. ``summary`` maps variant name -> metrics dict."""

    summary: dict[str, dict[str, Any]]
    rows: list[ResultRow]
    variants: list[str]
    baseline: str
    meta: dict[str, Any] = field(default_factory=dict)
    out_dir: Path | None = None

    def rows_for(self, variant: str) -> list[ResultRow]:
        return [r for r in self.rows if r.variant == variant]


def _fail_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _check_guard(guard: Guard, text: str, item: Item, mode: str) -> tuple[dict[str, Any], float, float]:
    """Run one guard. Returns (event, latency_ms, cost_usd). A raised error becomes event['error']."""
    event: dict[str, Any] = {"guard": guard.name, "stage": guard.stage}
    t0 = time.perf_counter()
    try:
        verdict = guard.check(text, item_id=item.id, prompt=item.prompt)
    except Exception as e:  # noqa: BLE001 - any guard failure must become "indeterminate", never a pass
        event.update(blocked=None, reason=None, error=_fail_text(e), latency_ms=0.0, latency_source="none")
        return event, 0.0, 0.0
    elapsed = round((time.perf_counter() - t0) * 1000, 3)
    if verdict.latency_ms is not None:  # a replayed recording knows its own latency
        latency, source = float(verdict.latency_ms), "replay"
    elif mode == "simulated" and guard.sim_latency_ms is not None:
        latency, source = simulated_latency(item.id, guard.name, guard.sim_latency_ms), "simulated"
    else:
        latency, source = elapsed, "measured"
    cost = guard.unit_cost_usd if verdict.cost_usd is None else verdict.cost_usd
    event.update(blocked=verdict.blocked, reason=verdict.reason, latency_ms=latency, latency_source=source)
    return event, latency, cost


def run_pair(item: Item, guards: list[Guard], target: Target, judge: RulesJudge, mode: str,
             variant: str) -> ResultRow:
    """Input guards (stop at the first block) -> target -> output guards -> refusal judge -> outcome."""
    events: list[dict[str, Any]] = []
    latency = cost = 0.0
    blocked_by: str | None = None
    failure: str | None = None
    answer = ""
    usage: dict[str, int] = {}
    called = False

    for g in (g for g in guards if g.stage == "input"):
        ev, lat, c = _check_guard(g, item.prompt, item, mode)
        events.append(ev)
        latency, cost = latency + lat, cost + c
        if ev.get("error"):
            failure = f"{g.name}: {ev['error']}"
            break
        if ev["blocked"]:
            blocked_by = f"{g.name}: {ev['reason']}"
            break

    if blocked_by is None and failure is None:
        called = True
        try:
            reply = target.call(item.prompt)
        except Exception as e:  # noqa: BLE001
            reply = TargetReply("", error=_fail_text(e))
        usage = dict(reply.usage)
        if reply.error:
            failure = f"target: {reply.error}"
        elif not reply.text.strip():
            failure = "target: empty response (a reasoning model may need a larger max_tokens)"
        else:
            answer = reply.text
        if failure is None:
            for g in (g for g in guards if g.stage == "output"):
                ev, lat, c = _check_guard(g, answer, item, mode)
                events.append(ev)
                latency, cost = latency + lat, cost + c
                if ev.get("error"):
                    failure = f"{g.name}: {ev['error']}"
                    break
                if ev["blocked"]:
                    blocked_by = f"{g.name}: {ev['reason']}"
                    break

    if failure is not None:
        outcome, evidence = INDETERMINATE, failure
    elif blocked_by is not None:
        outcome, evidence = classify(item.label, guard_blocked=True, model_refused=False), blocked_by
    else:
        refused, why = judge.judge(answer)
        outcome = classify(item.label, guard_blocked=False, model_refused=refused)
        evidence = why
    return ResultRow(id=item.id, variant=variant, label=item.label, lang=item.lang, category=item.category,
                     prompt=item.prompt, outcome=outcome, evidence=evidence,
                     guard_latency_ms=round(latency, 3), guard_cost_usd=round(cost, 6),
                     guard_events=events, target_called=called, usage=usage)


def variant_config_hash(cfg: Config, variant: Variant, mode: str) -> str:
    """Hash of everything that decides a variant's rows besides the prompts: its guards (in order),
    the target, the judge and the latency mode. Code behind a ``module:function`` is not hashed."""
    specs = {s.get("name"): s for s in cfg.guards}
    doc = {"guards": [specs[n] for n in variant.guards], "target": cfg.target, "judge": cfg.judge,
           "latency": mode}
    blob = json.dumps(doc, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _load_rows(path: Path) -> list[ResultRow]:
    """Read results.jsonl, skipping unreadable lines (for example a line cut short by a crash)."""
    rows: list[ResultRow] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(ResultRow.from_dict(json.loads(line)))
        except (json.JSONDecodeError, TypeError):
            continue
    return rows


def _write_rows(path: Path, rows: list[ResultRow]) -> None:
    tmp = path.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps(r.to_dict(), ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    os.replace(tmp, path)


def _in_file_order(items: list[Item], variants: list[Variant],
                   rows: dict[tuple[str, str], ResultRow]) -> list[ResultRow]:
    """The rows we have, in the order results.jsonl is written: item by item, variants in config order."""
    return [rows[(i.id, v.name)] for i in items for v in variants if (i.id, v.name) in rows]


def _select_variants(config: Config, only: list[str] | None) -> list[Variant]:
    if not only:
        return list(config.variants)
    names = [v.name for v in config.variants]
    unknown = [n for n in only if n not in names]
    if unknown:
        raise ConfigError(f"--only: unknown variant(s) {unknown}. Defined variants: {names}.")
    wanted = set(only) | {config.baseline}  # the baseline is always needed for the comparison
    return [v for v in config.variants if v.name in wanted]


def check_concurrency(value: object) -> int:
    """Return ``value`` when it is a whole number >= 1, otherwise raise a ConfigError that says what to give."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"concurrency must be a whole number >= 1 (1 = one pair at a time), got {value!r}.")
    return value


def _run_todo(todo: list[tuple[Item, Variant]], run_one: Callable[[Item, Variant], ResultRow],
              record: Callable[[Item, Variant, ResultRow], None], concurrency: int) -> None:
    """Run the pairs and hand every finished row to ``record``, which is only ever called from this thread.

    concurrency 1 is the plain loop. Above 1 the pairs run in worker threads; rows are recorded in completion
    order (the caller rewrites the file in config order afterwards). An error that escapes ``run_pair`` (Ctrl-C,
    a bug) cancels the pairs not started yet, still records the pairs that finish, and is raised again.
    """
    workers = min(concurrency, len(todo))
    if workers <= 1:
        for item, variant in todo:
            record(item, variant, run_one(item, variant))
        return
    failure: BaseException | None = None
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="guarddiff-pair") as pool:
        futures = {pool.submit(run_one, item, variant): (item, variant) for item, variant in todo}
        try:
            for fut in as_completed(futures):
                if fut.cancelled():
                    continue
                exc = fut.exception()
                if exc is not None:
                    if failure is None:
                        failure = exc
                        pool.shutdown(wait=False, cancel_futures=True)  # pairs not started are dropped
                    continue
                record(*futures[fut], fut.result())
        except BaseException:  # noqa: BLE001 - Ctrl-C in this thread: stop starting new pairs, then re-raise
            pool.shutdown(wait=False, cancel_futures=True)
            raise
    if failure is not None:
        raise failure


def run_ablation(config: Config | str | Path, out_dir: str | Path, *, latency: str | None = None,
                 fresh: bool = False, only: list[str] | None = None, concurrency: int = 1) -> RunResult:
    """Run the ablation and write ``results.jsonl``, ``summary.json`` and ``report.html`` into ``out_dir``.

    Resuming: a pair (item, variant) already in results.jsonl is reused when its prompt, label and settings
    hash are unchanged and its outcome was decided. ``indeterminate`` rows (a guard or the target failed) are
    always run again, because the cause may be fixed by now. ``fresh`` recomputes the selected variants.
    ``only`` runs those variants plus the baseline; rows of the other variants stay in results.jsonl as they are.
    ``latency`` overrides the config ("simulated" or "measured").
    ``concurrency`` is how many (item, variant) pairs run at the same time (default 1 = one after another).
    Guard and target functions must be thread-safe when it is above 1. The final files do not depend on it.
    """
    check_concurrency(concurrency)
    cfg = load_config(config) if isinstance(config, (str, Path)) else config
    mode = latency or cfg.latency
    if mode not in MODES:
        raise ConfigError(f"latency must be 'simulated' or 'measured', got {mode!r}.")
    items = load_items(cfg.items_path)
    variants = _select_variants(cfg, only)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    results_path = out / RESULTS_FILE

    used = {name for v in variants for name in v.guards}
    guards: dict[str, Guard] = {}
    target: Target | None = None
    try:
        for spec in cfg.guards:
            if spec.get("name") in used:
                guards[spec["name"]] = build_guard(spec, cfg.base_dir)
        target = build_target(cfg.target, cfg.base_dir)
        judge = RulesJudge(cfg.judge.get("patterns"))

        hashes = {v.name: variant_config_hash(cfg, v, mode) for v in variants}
        current = {(i.id, v.name): i for i in items for v in variants}  # the pairs this run must finish
        other_variants = {v.name for v in cfg.variants} - {v.name for v in variants}  # not chosen by --only
        item_ids = {i.id for i in items}

        latest: dict[tuple[str, str], ResultRow] = {}
        for r in _load_rows(results_path):
            latest[(r.id, r.variant)] = r  # if a pair appears twice, the later line wins

        done: dict[tuple[str, str], ResultRow] = {}  # rows of the chosen variants that can be reused
        kept: dict[tuple[str, str], ResultRow] = {}  # rows of other variants: written back untouched
        config_changed = retried = 0
        for key, r in latest.items():
            if r.variant in other_variants:
                if r.id in item_ids:
                    kept[key] = r  # --only must not throw away results that may have cost time or money
                continue
            it = current.get(key)
            if fresh or it is None or r.prompt != it.prompt or r.label != it.label:
                continue  # --fresh, a removed variant or item, or an edited prompt: not reusable
            if r.config_hash != hashes[r.variant]:  # settings changed since this row was written
                config_changed += 1
                continue
            if r.outcome == INDETERMINATE:  # it failed last time; the server or the code may be fixed now
                retried += 1
                continue
            done[key] = r
        # rewrite the file before running: drops stale or half-written lines, keeps other variants' rows
        _write_rows(results_path, _in_file_order(items, cfg.variants, {**kept, **done}))

        todo = [(i, v) for i in items for v in variants if (i.id, v.name) not in done]
        if todo:
            for g in guards.values():
                g.prepare()
            with results_path.open("a", encoding="utf-8") as fh:
                def run_one(item: Item, variant: Variant) -> ResultRow:
                    return run_pair(item, [guards[n] for n in variant.guards], target, judge, mode, variant.name)

                def record(item: Item, variant: Variant, row: ResultRow) -> None:
                    row.config_hash = hashes[variant.name]
                    done[(item.id, variant.name)] = row
                    fh.write(json.dumps(row.to_dict(), ensure_ascii=False) + "\n")
                    fh.flush()  # a crash loses at most the pairs in flight

                _run_todo(todo, run_one, record, concurrency)

        rows = [done[(i.id, v.name)] for i in items for v in variants]  # what this run compares
        _write_rows(results_path, _in_file_order(items, cfg.variants, {**kept, **done}))
        meta = {"schema": SCHEMA_VERSION, "baseline": cfg.baseline, "latency_mode": mode,
                "target_type": cfg.target.get("type", "mock"), "n_items": len(items),
                "skipped_pairs": len(items) * len(variants) - len(todo), "config_changed_pairs": config_changed,
                "retried_indeterminate_pairs": retried, "kept_other_pairs": len(kept),
                "kept_other_variants": [v.name for v in cfg.variants if any(k[1] == v.name for k in kept)]}
        return _finish(rows, [v.name for v in variants], cfg.baseline, meta, out)
    finally:
        for g in guards.values():
            g.close()
        if target is not None:
            target.close()


def _finish(rows: list[ResultRow], variants: list[str], baseline: str, meta: dict[str, Any],
            out: Path) -> RunResult:
    by_variant = {v: [r for r in rows if r.variant == v] for v in variants}
    summary = build_summary(by_variant, baseline)
    meta = {**meta, "variants": variants}
    doc = {**meta, "summary": summary}
    (out / SUMMARY_FILE).write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = RunResult(summary=summary, rows=rows, variants=variants, baseline=baseline, meta=meta, out_dir=out)
    from .report.html import write_html  # noqa: PLC0415 - keeps the import graph one-directional

    write_html(result, out / "report.html")
    return result


def load_run(out_dir: str | Path) -> RunResult:
    """Rebuild a RunResult from an output folder, for ``guarddiff report``."""
    out = Path(out_dir)
    results_path, summary_path = out / RESULTS_FILE, out / SUMMARY_FILE
    if not results_path.is_file():
        raise GuarddiffError(f"{results_path} not found. Run `guarddiff run CONFIG --out {out}` first.")
    rows = _load_rows(results_path)
    if not rows:
        raise GuarddiffError(f"{results_path} has no readable rows. Re-run with --fresh.")
    meta: dict[str, Any] = {}
    if summary_path.is_file():
        try:
            loaded = json.loads(summary_path.read_text(encoding="utf-8"))
            meta = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            meta = {}
    seen: list[str] = []
    for r in rows:
        if r.variant not in seen:
            seen.append(r.variant)
    variants = [v for v in meta.get("variants", seen) if v in seen] or seen
    rows = [r for r in rows if r.variant in variants]  # after `run --only`, other variants' rows are kept aside
    baseline = meta.get("baseline") if meta.get("baseline") in variants else variants[0]
    meta = {k: v for k, v in meta.items() if k != "summary"}
    by_variant = {v: [r for r in rows if r.variant == v] for v in variants}
    return RunResult(summary=build_summary(by_variant, baseline), rows=rows, variants=variants,
                     baseline=baseline, meta={**meta, "variants": variants, "baseline": baseline}, out_dir=out)
