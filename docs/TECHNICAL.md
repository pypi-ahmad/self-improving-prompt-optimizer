# Technical Reference

## Contracts and validation

`TaskContract` contains `task_description`, `base_prompt`, `constraints`, and `protected_literals`. `ModelSettings` contains the model ID, reasoning effort, optional temperature, and maximum completion tokens. Evaluation records contain a status, prompt, nullable metrics, per-case results, eligibility, cross-case spread, and repeatability.

The app deep-copies the contract and configuration at initialization. Protected prompt literals must occur in the base prompt and every generated or injected candidate. Output literals are separate benchmark checks.

The JSON parser accepts one complete JSON value, optionally enclosed in one Markdown fence. It rejects surrounding prose and nonfinite JSON constants. Judges must return exactly the four numeric metrics plus a nonempty `rationale`. Scores must be finite numbers from 1 to 10; booleans and numeric strings are invalid.

Benchmark bundles use version 1, a task fingerprint, `optimization` and `holdout` arrays, and a content hash. Case IDs and normalized inputs must be unique. The importer supports legacy lists with at least four cases, sorting them by fingerprint before splitting. Invalid custom data does not fall back to the default task. Optional JSON Schemas are validated locally and cannot fetch external references.

## Search and evaluation

The active population never exceeds its configured limit. Up to half the population is carried as elites; injections consume free slots before mutations and crossover. Excess injections remain queued. Baseline evaluation is independent of this population.

Variation generation uses the original contract, relevant sections of both guidance documents, parent prompts, and up to three optimization-case failures for each parent. High-strength changes must still preserve the contract. It does not use holdout results.

Search cache keys hash the exact prompt, contract, entire benchmark hash, guidance hashes, model settings, and evaluator version. Only complete evaluations are cached. Finalist and holdout evaluations bypass that cache. Embeddings are reused within a run; carried elites are not compared against their own vectors.

Per-case statuses are `complete`, `check_failed`, `generation_failed`, `judge_failed`, and `budget_skipped`. Hard-check failures can retain valid judge scores for inspection, but they are ineligible for selection. A candidate with a missing score is incomplete and has no aggregate score. Failures never become neutral scores.

Weighted selection uses normalized accuracy, clarity, conciseness, and helpfulness weights. Pareto selection uses those four dimensions only. Hybrid selection prioritizes the Pareto front and fills remaining archive slots by weighted score. Cross-case spread is the standard deviation of mean case scores. Repeatability is the mean within-case standard deviation across fresh repetitions; it is absent for single evaluations.

Search stops at the generation limit, when the last three best scores span less than 0.05, or when remaining allowance is needed for estimated final validation. Finalists are the baseline and up to two distinct non-baseline elites, evaluated twice each. Ties favor the baseline. The selected prompt and baseline receive two holdout evaluations each; identical prompts share the same result.

The comparison recommends a candidate only when all required validation completes, weighted holdout quality improves, mean accuracy does not fall, and all candidate hard checks pass. Individual regressions remain visible. The comparison is an observation, not a significance test.

## Provider calls and accounting

`Runtime.call(role, messages, phase)` returns status, response text, a usage event ID, and sanitized error metadata when applicable. Every billable operation uses the runtime. Chat completion limits are 8,192 tokens for generation/benchmark requests and 4,096 for candidate/judge requests, including reasoning tokens. Default Luna/Terra requests set medium reasoning effort, omit temperature, and use the default service tier.

The runtime reserves an input bound based on serialized UTF-8 bytes plus message framing, priced as uncached input, along with maximum output cost. A shared lock admits reservations atomically, and a semaphore limits in-flight requests. Actual cost is `(uncached input * input rate + cached input * cached rate + completion tokens * output rate) / 1,000,000`. Reasoning is already included in completion usage.

Unknown usage retains the full reservation. Reported usage that exceeds a reservation stops further dispatch. Custom models require finite, nonnegative rates; unpriced embeddings are skipped. Rate estimates are not provider billing guarantees.

SDK retries are disabled. The runtime allows one counted retry for HTTP 429, server errors, and connection/timeouts; each attempt has a fresh reservation. Ordinary parse failures and unsupported parameters do not trigger a retry or model substitution. Provider error bodies are excluded from UI logs and exports.

## Exports and verification

Full exports have `schema_version: 1`, the graph state, live usage snapshot, configured prices, price source, and concurrency. They include guidance text/hashes and every benchmark split. They cannot restore in-memory checkpoints.

The live verification ledger is saved before dispatch with a temporary file and atomic replacement. A restarted smoke test inherits earlier charges and pending reservations. The smoke test is limited to 80 attempts and $6 across executions that use the same ledger. Offline tests use fake providers and never need service credentials.
