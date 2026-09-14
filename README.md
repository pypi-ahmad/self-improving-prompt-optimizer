# Self-Improving Prompt Optimizer

Self-Improving Prompt Optimizer is an agentic system that iteratively evolves and refines system prompts across generations. Orchestrated with LangGraph and evaluated using multi-objective LLM-as-judge scoring, the application mutates, crosses over, diversity-filters, and selects candidate prompts against a test benchmark through an interactive Streamlit web interface.

## Requirements

- Python: `>=3.13` (specified in `pyproject.toml` and `.python-version`)
- Package manager: [uv](https://docs.astral.sh/uv/)
- Dependencies (from `pyproject.toml`):
  - `langchain>=1.3.15`
  - `langchain-openai>=1.5.0`
  - `langgraph>=1.2.11`
  - `python-dotenv>=1.2.2`
  - `streamlit>=1.61.1`
- External API access: An OpenAI-compatible API endpoint providing chat completions and vector embeddings (`text-embedding-3-small`).

## Setup and run commands

### Installation (cross-platform)

Clone the repository and install dependencies using `uv`:

```bash
git clone https://github.com/pypi-ahmad/self-improving-prompt-optimizer.git
cd self-improving-prompt-optimizer
uv sync
```

### Running the application (cross-platform)

Ensure environment variables are configured, then launch the Streamlit server:

```bash
uv run streamlit run app.py
```

The web interface serves by default at `http://localhost:8531` (configured in `.streamlit/config.toml`).

### Automated launcher (Windows only)

On Windows systems, a batch script is provided to automate environment initialization and startup:

```cmd
run_app.cmd
```

`run_app.cmd` performs the following steps:
1. Installs `uv` via PowerShell if not found on the system PATH.
2. Copies `.env.example` to `.env` if `.env` is absent.
3. Warns if `OPENAI_API_KEY` is not set.
4. Executes `uv sync`.
5. Starts Streamlit on port `8531`.

## Configuration

### Environment variables

The application reads configuration from system environment variables and `.env` (loaded via `python-dotenv`). System environment variables take precedence over values in `.env`.

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | API key for the OpenAI or OpenAI-compatible endpoint. The application halts at startup if unset. |
| `OPENAI_BASE_URL` | No | Base URL for the OpenAI-compatible endpoint. Defaults to `https://api.openai.com/v1` if unset. |
| `AGNES_API_KEY` | No | API key for Agnes AI. If set, exposes `agnes-2.5-flash` (`https://apihub.agnes-ai.com/v1`) as a selectable model in the UI dropdown. |

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
- `.streamlit/config.toml`: Pins the server port to `8531`.

## Repository map

```
self-improving-prompt-optimizer/
├── app.py                 # Streamlit UI, sidebar controls, step execution, and data exports
├── graph.py               # LangGraph state machine, 7 optimization nodes, and checkpointer
├── evaluator.py           # Model and embedding client factory, candidate execution, and scoring
├── benchmark.py           # Static 8-case benchmark, loader, saver, and auto-generation
├── prompts.py             # Default prompts and JSON-only meta-prompt templates
├── utils.py               # Pure-stdlib helper functions (Pareto front, cosine similarity, weights)
├── run_app.cmd            # Windows-only automated setup and launch script
├── pyproject.toml         # Project metadata and dependency definitions
├── uv.lock                # Locked dependency tree
├── .python-version        # Pinned Python version (3.13)
├── .env.example           # Environment variable template
├── .streamlit/
│   └── config.toml        # Streamlit server port configuration (8531)
├── data/
│   └── generated_benchmark.json  # Runtime auto-generated benchmark (git-ignored)
└── docs/
    ├── ARCHITECTURE.md    # System architecture, state schema, data flow, and external dependencies
    ├── TECHNICAL.md       # Implementation details, invariants, error handling, and persistence
    ├── RUNBOOK.md         # Operational procedures, startup/shutdown, and troubleshooting
    └── CONTRIBUTING.md    # Development setup, branch conventions, and testing expectations
```

## How to run tests

There is no automated test suite in this repository. The project contains no `tests/` directory, no unit test framework in `pyproject.toml`, and no continuous integration (CI) pipeline.

Testing must be conducted manually against a running instance of the application:

1. Launch the application with `uv run streamlit run app.py`.
2. Configure a test run in the sidebar and click **Start Optimization**.
3. Verify that generations advance, metrics update, and no unhandled exceptions are raised.
4. Verify that the **Best Prompt**, **Pareto Front**, and **History** tabs render expected tables and charts.
5. Verify that downloaded files (`best_prompt.txt`, `history.json`, `history.csv`) contain valid records.

## Known limitations

- **In-memory state persistence**: Optimization state is stored exclusively in process memory via LangGraph's `InMemorySaver`. Shutting down the server or starting a new run discards all candidate history, Pareto front records, and cached evaluation scores.
- **Sequential evaluation**: Candidates are evaluated against benchmark cases sequentially in a loop. There is no concurrent batching or asynchronous API dispatch across test cases.
- **Exact-match cache keys**: The score cache keys entries strictly on the exact prompt string. Minor whitespace or formatting variations result in a cache miss and trigger full re-evaluation.
- **Hardcoded embedding model**: Embeddings use `text-embedding-3-small`. If an OpenAI-compatible endpoint does not support embeddings or this specific model identifier, vector retrieval fails and diversity filtering is skipped.
- **Elite pool minimum floor**: Multi-objective selection floors the elite pool capacity at `max(population_size, 3)`. Setting `population_size` to 2 results in 3 elites being carried forward, exceeding the requested population count before variations are generated.
- **Destructive benchmark regeneration**: Triggering auto-generation overwrites `data/generated_benchmark.json` without versioning or history backups.
- **No automated test harness**: Verification relies entirely on manual local execution.

## Documentation

Detailed documentation is available in the `docs/` directory:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): System architecture, execution flow diagrams, state schema, and external services.
- [docs/TECHNICAL.md](docs/TECHNICAL.md): Detailed module implementations, operational invariants, error recovery, and persistence paths.
- [docs/RUNBOOK.md](docs/RUNBOOK.md): Operational guide, start/stop procedures, common errors, and diagnostics.
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md): Contribution guidelines, local setup, branch conventions, and PR requirements.

Additional project documents:
- [DISCLAIMER.md](DISCLAIMER.md): Data responsibility and warranty disclaimer.
- [SECURITY.md](SECURITY.md): Vulnerability reporting procedures.
- [SUPPORT.md](SUPPORT.md): Support expectations and guidelines.
- [LICENSE](LICENSE): MIT License terms.
