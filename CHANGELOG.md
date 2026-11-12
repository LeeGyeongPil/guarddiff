# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [Unreleased]

## [0.3.0] - 2026-11-12

### Added
- Output language: English or Korean. Pick it with `--lang en|ko` (before or after the sub-command) or the `GUARDDIFF_LANG` environment variable, or let it follow `LC_ALL`, `LC_MESSAGES` and `LANG` (the first one that is set decides; a value starting with `ko` means Korean, anything else English). Help text, argparse messages, progress lines, warnings, error messages and the Markdown and HTML reports are translated; the HTML report sets `<html lang>`.
- `guarddiff.i18n`: the single message table (`MESSAGES`), `t()` and `resolve_lang()`.
- `gate` limit options now have help text.

### Notes
- Machine-readable data is the same in every language: `report --format json`, `summary.json` and `results.jsonl` (including the failure strings stored there). Scripts that compare printed text should pin `--lang en` or `GUARDDIFF_LANG=en`.

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
