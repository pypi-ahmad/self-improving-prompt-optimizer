# Usage Guide

## Start the application

Run `uv sync`, then `uv run streamlit run app.py`. On Windows, `run_app.cmd` performs setup and starts the same application. The configured address is `http://localhost:7080`.

The server reads `OPENAI_API_KEY` and optional `OPENAI_BASE_URL` from the process environment, falling back to an existing `.env`. Environment values take precedence. The app checks model availability with actual requests and never silently substitutes another model.

Double-click `run_app.cmd` to launch with the dark theme. The launcher forcibly stops processes listening on port 7080 before starting this app. If it cannot clear the port, it reports an error and does not start another server. Manual `streamlit run` uses the configured port and theme but does not clear an occupied port.

## Configure and prepare

Click **ⓘ** beside the app title for a getting-started guide. Smaller guides appear beside Configuration, Benchmark, the run controls, and Results. Opening help neither changes the run nor makes API calls.

1. Enter the task, base prompt, and required constraints. Protected prompt literals must already occur in the base prompt; enter one per line.
2. Keep the Luna medium generation/candidate settings and Terra medium judge settings, or enter other provider-supported model IDs. Custom models need prices and compatible reasoning/temperature settings.
3. Choose population size, generation count, mutation strength, and selection strategy. Four metric weights control ranking; cross-case spread and repeatability are diagnostics only.
4. Set the USD allowance, maximum API attempts, and concurrency. Defaults are $6, 1,000 attempts, and four concurrent requests. Prices in the editable table are USD per million tokens. Add a `text-embedding-3-small` row if semantic filtering is wanted; otherwise exact deduplication is used.
5. Choose a benchmark source and click **Prepare benchmark**, or click **Start Optimization** to prepare and start together.

Both skills are always active through the repository's `guidance/` files. The app includes the relevant sections in generation, judging, and benchmark messages. No local skill installation is required.

Preparation freezes the settings and starts the run's allowance. A repeated failed generation uses the same allowance. **New run** discards the current session's run and creates a fresh allowance when preparation begins again.

## Benchmark sources

| Source | Behavior |
|---|---|
| Built-in | 12 optimization cases and four holdout cases for the default message-rewriting task |
| Generate | Luna creates both splits; a valid bundle is saved to `data/generated_benchmark.json` |
| Import JSON | Validate an uploaded bundle or legacy case list; invalid content never falls back to built-in cases |
| Saved generated | Load the saved bundle only when its task fingerprint matches the current contract |

**Download benchmark (.json)** exports the prepared bundle for inspection or editing. Versioned bundles bind to the entire contract, including base prompt and constraints. For a new task, generate a new benchmark or provide a fresh unbound object containing `optimization` and `holdout` arrays. Legacy lists require at least four unique cases and are split reproducibly, with approximately one quarter held out.

Each case contains `id`, `input`, `guideline`, `category`, and `checks`. IDs and normalized input texts must be unique across both splits. Empty inputs are allowed for edge cases; guidelines cannot be empty.

Optional checks are `required_literals` and `forbidden_literals` arrays and `json_schema`. Required/forbidden literals are case-sensitive output checks. JSON Schemas are checked before model calls and cannot load external references. Unknown check fields are rejected. Add checks only for requirements the task actually establishes.

## Run and pause

Starting evaluates the original prompt on optimization cases. **Run continuously** is enabled by default; uncheck it to use **Run next stage**. Each step advances a generation, finalist evaluation, or holdout evaluation.

**Stop** pauses between stages; it does not cancel in-flight provider requests. **Resume** continues the same checkpoint and allowance. During search, **Inject** queues a custom candidate. Excess injections stay queued; protected literals and diversity checks still apply.

At most half the population carries forward as elites, leaving slots for injections and new variations. Search stops at its generation limit, after three sufficiently flat best scores, or when the estimated remaining validation work needs the allowance.

After search, the baseline and top two distinct non-baseline candidates are evaluated twice on optimization cases. Selection uses their fresh mean scores; ties favor the baseline. Only that selected prompt and the baseline are then evaluated twice on holdout cases. No holdout evidence enters another mutation or finalist selection.

## Review and export

- **Best Prompt** shows the strongest optimization result, which may differ from the final recommendation.
- **Comparison** shows the recommendation, finalist repeatability, holdout regressions, and baseline/candidate outputs side by side. A qualifying improvement requires complete validation, higher weighted holdout quality, no mean accuracy reduction, and passing hard checks.
- **Pareto Front** shows non-dominated eligible candidates.
- **History** includes valid, invalid, and incomplete evaluations, with per-case checks and explanations.

Download the best or recommended prompt as text, history as JSON/CSV, and the complete run as versioned JSON. Complete exports include settings, guidance hashes/text, benchmark splits, outputs, scores, usage, and prices. They are inspection artifacts and cannot resume a checkpoint.

Usage panels separate provider-reported costs from conservative reservations. Missing token usage keeps the full reservation. Retries count as new attempts. Truncated, malformed, or failed judgments do not receive invented scores. If any required validation is unfinished, the comparison is labeled incomplete and the recommendation remains the baseline.

For operational issues, see [the runbook](docs/RUNBOOK.md). Task content leaves the machine for provider calls and may appear in explicit exports; see [the disclaimer](DISCLAIMER.md).
