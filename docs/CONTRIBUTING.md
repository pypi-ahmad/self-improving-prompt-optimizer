# Contributing

## Local setup

Use Python 3.13 and uv. Run `uv sync` from the repository root to install the locked runtime and development dependencies. After configuring the provider environment, launch with `uv run streamlit run app.py`. Do not commit `.env`, generated benchmark data, or verification artifacts.

## Required checks

```bash
uv run pytest -q
uv run ruff check app.py benchmark.py contracts.py evaluator.py graph.py prompts.py reporting.py runtime.py tests scripts
uv run ty check app.py benchmark.py contracts.py evaluator.py graph.py prompts.py reporting.py runtime.py scripts
git diff --check
```

Tests use fake providers and Streamlit AppTest. Cover the changed behavior, particularly budget reservations and retries, failed judgments, benchmark isolation, score-cache fingerprints, and checkpointed UI controls. Offline tests must never make billable calls.

For a live check, obtain a spending allowance first. `uv run python -m scripts.live_smoke` uses Luna medium and Terra medium, two generations, population four, two optimization cases, two holdout cases, and balanced final validation. It shares an 80-attempt/$6 ledger across restarts at `artifacts/verification_budget.json`. Do not reset that file to evade the allowance. Inspect safe artifact metadata before retrying a failed run, then report the actual attempts and estimated cost.

## Contribution boundaries

The target branch is `main`. Branches, commits, pushes, and pull requests require the repository owner's authorization in agent workflows. No CI workflow is currently configured.

Preserve unrelated work, existing provider credential names, and the local-first architecture. Keep the skill adaptations portable; do not add absolute paths to a personal skill directory. Changes to guidance must be reflected in its version/provenance and tested through the messages actually sent to models.

Update usage, architecture, and data-handling documentation when behavior changes. Distinguish offline checks, live workflow checks, and measured prompt-quality comparisons in reports. A successful API request does not prove a prompt improves arbitrary tasks.
