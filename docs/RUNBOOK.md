# Runbook

## Start and stop

Run `uv sync`, then `uv run streamlit run app.py`. The configured address is `http://localhost:7080`. Windows users can use `run_app.cmd`. It checks for uv, creates `.env` from the example only when no environment API key or `.env` is present, synchronizes dependencies, and launches Streamlit.

The app reads `OPENAI_API_KEY` and optional `OPENAI_BASE_URL` from the process environment, with existing `.env` values as a fallback. After changing Windows environment variables, relaunch the server so it inherits them. Do not paste credential values into diagnostic reports.

The Windows launcher clears port 7080 by forcibly stopping listening processes, then starts Streamlit with the dark theme. It stops if process termination fails or the port remains occupied. A protected or elevated listener may require the appropriate Windows privileges. Manual startup does not terminate an existing listener.

Use **Prepare benchmark** to freeze settings and obtain a benchmark, then **Start Optimization**. Starting also prepares automatically if needed. **Run continuously** advances stages; disable it for **Run next stage**. **Stop** and **Resume** operate at stage boundaries. **New run** discards the active in-memory run and permits a new allowance. Download results before replacing a run or stopping the server with Ctrl+C.

## Diagnostics

The app shows the last 60 search log entries, per-case evaluation statuses, and usage events grouped by model and phase. Provider error details are limited to type and HTTP status; raw exception bodies are not displayed.

| Symptom | Action |
|---|---|
| Missing `OPENAI_API_KEY` | Configure it in the server environment or existing `.env`, then restart |
| Preparation fails | Check uploaded JSON, case IDs, unique inputs, schema checks, task fingerprint, and provider settings; invalid custom data never falls back |
| Custom model cannot start | Add its input/cached-input/output prices and select parameters supported by that endpoint |
| `generation_failed` or `judge_failed` | Inspect the sanitized request event and case status; unsupported models/parameters are not substituted automatically |
| `check_failed` | Inspect required/forbidden literals or the output schema; the candidate is excluded from selection |
| `budget_skipped` or incomplete comparison | The allowance cannot admit further work; export the partial run, then configure an appropriate new run |
| Semantic diversity unavailable | Add supported embedding model prices if desired; exact deduplication remains active |
| Search stops early | Check generation limit, the three-generation plateau, and estimated remaining validation allowance |
| Settings are disabled | Preparation has frozen them; use New run to change the contract or model settings |
| Stop is not immediate | In-flight provider requests complete before the next stage boundary |

An incomplete comparison retains the baseline recommendation. A complete comparison without a qualifying improvement also retains the baseline. Both are valid results.

## Storage and recovery

Application run checkpoints exist only in memory. Browser exports contain inspectable configuration and results, but cannot resume the graph after a server restart. Generated benchmarks live in `data/generated_benchmark.json` and are overwritten only after successful generation. Back up useful bundles with the download button.

The explicit live check `uv run python -m scripts.live_smoke` writes ignored artifacts under `artifacts/`. Its `verification_budget.json` keeps the 80-attempt/$6 allowance across restarts. Do not delete that ledger to bypass an authorized verification limit. `live_smoke.json` contains the latest completed stage's run export.

For offline verification use the commands in [CONTRIBUTING.md](CONTRIBUTING.md). For data handling and price-estimate limits, see [../DISCLAIMER.md](../DISCLAIMER.md).
