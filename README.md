# Self-Improving Prompt Optimizer

Self-Improving Prompt Optimizer improves system prompts in a local Streamlit app. LangGraph coordinates mutation, crossover, independent judging, repeated finalist evaluation, and a final comparison on unseen holdout cases. Repository-owned adaptations of Prompt Customizer and Prompt Engineer guide generation and evaluation while preserving the original task.

By default, `gpt-5.6-luna` generates and executes candidates and `gpt-5.6-terra` judges them, both with medium reasoning effort. Each run has a $6 allowance, a 1,000-attempt limit, and at most four concurrent requests. These settings are configurable before preparation begins.

## Requirements

- Python: `>=3.13` (specified in `pyproject.toml` and `.python-version`)
- Package manager: [uv](https://docs.astral.sh/uv/)
- Dependencies (from `pyproject.toml`):
  - `langchain>=1.3.15`
  - `langchain-openai>=1.5.0`
  - `langgraph>=1.2.11`
  - `python-dotenv>=1.2.2`
  - `streamlit>=1.61.1`
  - `jsonschema>=4.26.0`
  - `referencing>=0.37.0`
  - `openai>=3.0.0`
- External API access: An OpenAI-compatible chat-completions endpoint supporting the selected models and request parameters. Embeddings are optional; unpriced or unavailable embeddings are skipped.

## Setup and run commands

### Installation (cross-platform)

Clone the repository, then install its dependencies with `uv`:

```bash
git clone https://github.com/pypi-ahmad/self-improving-prompt-optimizer.git
cd self-improving-prompt-optimizer
uv sync
```

### Running the application (cross-platform)

Configure the environment variables, then start the Streamlit server:

```bash
uv run streamlit run app.py
```

The web interface serves by default at `http://localhost:7080` (configured in `.streamlit/config.toml`).

### Automated launcher (Windows only)

Windows users can use the batch script to prepare the environment and start the app:

```cmd
run_app.cmd
```

`run_app.cmd`:
1. Installs `uv` via PowerShell if not found on the system PATH.
2. Copies `.env.example` to `.env` only if both `.env` and an environment API key are absent.
3. Warns if `OPENAI_API_KEY` is not set.
4. Executes `uv sync`.
5. Stops existing processes listening on port `7080`; aborts if the port cannot be cleared.
6. Starts Streamlit at `http://localhost:7080` with the dark theme.

## Configuration

### Environment variables

The application reads configuration from system environment variables and `.env` (loaded via `python-dotenv`). System environment variables take precedence over values in `.env`.

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | API key for the OpenAI or OpenAI-compatible endpoint. The app stops at startup if it is unset. |
| `OPENAI_BASE_URL` | No | Base URL for the OpenAI-compatible endpoint. Defaults to `https://api.openai.com/v1` if unset. |
| `AGNES_API_KEY` | No | Used when a model field is set to `agnes-2.5-flash`; requests go to `https://apihub.agnes-ai.com/v1`. Configure its prices and supported parameters before starting. |

An example template is provided in `.env.example`:

```bash
# Copy to .env and populate keys
OPENAI_API_KEY=sk-your-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
AGNES_API_KEY=your-agnes-key-here
```

### Configuration files

- `.env`: Local environment file (ignored by version control).
- `.env.example`: Reference configuration template.
- `.streamlit/config.toml`: Pins the server port to `7080`.

## Repository map

```
self-improving-prompt-optimizer/
├── app.py                 # Streamlit UI, sidebar controls, step execution, and data exports
├── graph.py               # Checkpointed search, finalist, and holdout stages
├── evaluator.py           # Candidate execution, independent judging, and aggregation
├── runtime.py             # Provider calls, concurrency, retry accounting, and budget reservations
├── contracts.py           # Immutable task data, skill loading, and output validation
├── reporting.py           # Versioned run exports and history formats
├── benchmark.py           # 12 optimization cases, 4 holdout cases, import and generation
├── prompts.py             # Role-specific messages assembled from the skill guidance
├── guidance/              # Portable, versioned adaptations of both supplied skills
├── tests/                 # Offline provider, workflow, budget, and Streamlit tests
├── scripts/live_smoke.py  # Explicit live check with a persistent 80-call / $6 allowance
├── utils.py               # Pure-stdlib helper functions (Pareto front, cosine similarity, weights)
├── run_app.cmd            # Windows-only automated setup and launch script
├── pyproject.toml         # Project metadata and dependency definitions
├── uv.lock                # Locked dependency tree
├── .python-version        # Pinned Python version (3.13)
├── .env.example           # Environment variable template
├── .streamlit/
│   └── config.toml        # Streamlit server port configuration (7080)
├── data/
│   └── generated_benchmark.json  # Runtime auto-generated benchmark (git-ignored)
└── docs/
    ├── ARCHITECTURE.md    # System architecture, state schema, data flow, and external dependencies
    ├── TECHNICAL.md       # Implementation details, invariants, error handling, and persistence
    ├── RUNBOOK.md         # Operational procedures, startup/shutdown, and troubleshooting
    └── CONTRIBUTING.md    # Development setup, branch conventions, and testing expectations
```

## How to run tests

Offline tests mock all providers, including Streamlit AppTest workflows:

```bash
uv run pytest -q
uv run ruff check app.py benchmark.py contracts.py evaluator.py graph.py prompts.py reporting.py runtime.py tests scripts
uv run ty check app.py benchmark.py contracts.py evaluator.py graph.py prompts.py reporting.py runtime.py scripts
```

`uv run python -m scripts.live_smoke` makes real API calls. It uses a shared ledger at `artifacts/verification_budget.json`, capped at 80 attempts and $6 across restarts, and writes a sanitized run export to `artifacts/live_smoke.json`. Read [the contributor guide](docs/CONTRIBUTING.md) before running it. CI is not configured.

## Evaluation and prices

Selection uses accuracy, clarity, conciseness, and helpfulness. Cross-case spread and repeatability are diagnostics rather than ranking objectives. Invalid judgments do not become neutral scores. Incomplete evaluations and hard-check failures cannot enter the elite pool.

After search, the baseline and top two non-baseline candidates receive two fresh evaluations on optimization cases. The selected prompt and baseline then receive two evaluations on holdout cases. Holdout results never enter mutation feedback or choose a different finalist. **Comparison** displays the recommendation, per-case outputs, regressions, and incomplete validation explicitly.

Default prices are user-supplied USD rates per million tokens:

| Model | Input | Cached input | Output |
|---|---:|---:|---:|
| `gpt-5.6-luna` | $0.20 | $0.02 | $1.20 |
| `gpt-5.6-terra` | $2.00 | $0.20 | $12.00 |

Before each attempt, the runtime reserves uncached input and maximum completion costs, then reconciles reported usage. It keeps the reservation when usage is missing. Completion tokens include reasoning. Estimated charges depend on configured rates and provider metering; they do not limit account-wide billing.

## Known limitations

- **In-memory state persistence**: Optimization state is stored exclusively in process memory via LangGraph's `InMemorySaver`. Shutting down the server or starting a new run discards all candidate history, Pareto front records, and cached evaluation scores.
- **Provider-dependent judgments**: Scores and repeated-run differences are observations, not ground truth or statistical significance claims.
- **Budget-limited validation**: A small allowance, large prompts, or provider failures can leave validation incomplete. The recommendation remains the baseline.
- **Exact text caching**: Search cache fingerprints include the prompt, contract, benchmark, guidance, and model settings. Whitespace changes still trigger a new evaluation.
- **Optional semantic diversity**: `text-embedding-3-small` needs an explicit price row and provider support. Otherwise exact deduplication applies.
- **Destructive benchmark regeneration**: Triggering auto-generation overwrites `data/generated_benchmark.json` without versioning or history backups.
- **Session-only continuation**: Run JSON exports support inspection and reproduction of settings, but cannot restore in-memory graph checkpoints.

## Documentation

The `docs/` directory contains detailed documentation:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): System architecture, execution flow diagrams, state schema, and external services.
- [docs/TECHNICAL.md](docs/TECHNICAL.md): Detailed module implementations, operational invariants, error recovery, and persistence paths.
- [docs/RUNBOOK.md](docs/RUNBOOK.md): Operational guide, start/stop procedures, common errors, and diagnostics.
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md): Contribution guidelines, local setup, branch conventions, and PR requirements.

Additional project documents:
- [DISCLAIMER.md](DISCLAIMER.md): Data responsibility and warranty disclaimer.
- [SECURITY.md](SECURITY.md): Vulnerability reporting procedures.
- [SUPPORT.md](SUPPORT.md): Support expectations and guidelines.
- [LICENSE](LICENSE): MIT License terms.
