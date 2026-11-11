# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [Unreleased]

## [0.2.0] - 2026-11-11

### Added
- `guarddiff run --concurrency N` and `run_ablation(..., concurrency=N)`: run N (item, variant) pairs at the same time. The default 1 keeps the old sequential behavior; final `results.jsonl`, `summary.json` and the report do not depend on N. Values below 1 or non-integers are rejected (exit code 2 on the CLI). With measured latency and N > 1 a warning is printed to stderr.

## [0.1.0] - 2026-11-11

### Added
- `guarddiff run | report | gate | demo | init` commands.
- Seven outcomes that separate guard blocks from the model's own refusals, plus `indeterminate`.
- Metrics: ASR, over-block rate, Wilson 95% intervals, exact McNemar test, latency p50/p95, guard cost.
- Guards: `regex`, `python`, `replay`, `hf-qwen3guard` (optional extra). Targets: `mock`, `python`, `openai`.
- `gate` fails by default when any item is indeterminate (`--allow-indeterminate` to opt out); the `run` table marks such variants with `!`.
- Resume re-runs only variants whose guard, target, judge or latency-mode config changed. Pairs that ended `indeterminate` are always re-run (`retry N indeterminate pairs`), so fixing the cause and running again is enough.
- `run --only` keeps the stored results of the variants it did not run (`kept N pairs …`).
- `gate` exits 2 when `--allow-indeterminate` and `--max-indeterminate` are combined; allowing indeterminate items prints a note. `report --format md` and `report.html` mark variants with indeterminate items with `!` and a warning line.
- Resumable `results.jsonl`, `summary.json`, single-file `report.html`, Markdown summary.
- Bundled 18-prompt English/Korean set (CC0-1.0) and offline, recorded-replay and live examples.
