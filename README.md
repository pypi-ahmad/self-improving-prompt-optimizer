# Self-Improving Prompt Optimizer

An agentic system that evolves a system prompt across generations — mutating, evaluating, and selecting candidates with multi-objective LLM-as-judge scoring — until it converges on the best-performing version against a fixed benchmark.

![Python](https://img.shields.io/badge/Python-3.13%2B-blue)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B)
![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-1C3C3C)
![LangChain](https://img.shields.io/badge/LangChain-langchain--openai-1C3C3C)
![uv](https://img.shields.io/badge/Package%20Manager-uv-de5fe9)

**Repository:** https://github.com/pypi-ahmad/self-improving-prompt-optimizer

## Features

- **Multi-objective LLM-as-judge scoring** — every candidate prompt is judged on `accuracy`, `clarity`, `conciseness`, and `helpfulness` (1–10, per benchmark case); `consistency` is derived from the variance of those scores across cases.
- **Three selection strategies** — `Weighted Score` (top-N by weighted sum), `Pareto Front` (non-dominated solutions only), or `Hybrid` (default: union of both, capped).
- **User-adjustable metric weights** — five sliders recompute the weighted score live, even for prompts scored earlier in the run.
- **Mutation + crossover** — an LLM rewrites elite prompts (mutation) and blends pairs of elites (crossover) to fill each new generation.
- **Embedding-based diversity control** — candidates whose embedding is too similar (cosine similarity above a threshold) to an existing elite are rejected, preventing population collapse into near-duplicates.
- **Elitism + score caching** — elites carried forward unchanged are read from a cache instead of being re-judged, cutting redundant API calls.
- **Plateau + max-generation stopping** — the run stops automatically once the best score has been flat for 3 generations or the generation limit is reached.
- **Pause, stop, and mid-run injection** — the LangGraph workflow is checkpointed and pauses between generations, so you can stop a run cleanly or inject your own custom prompt into the next generation, with no background threads involved.
- **Fixed or auto-generated benchmark** — ship with 8 built-in test cases, or click a button to have the LLM design a new 6–8 case benchmark from a task description (saved to `data/generated_benchmark.json` for reuse).
- **Live progress, logs, and history** — generation counter, best score, elite size, Pareto front size, a scrollable log, a full evaluation history table, and per-test-case drill-down for any prompt ever scored.
- **Exports** — download the best prompt as `.txt`, and the full run history as `.json` or `.csv`.

## Demo / Screenshots

_No screenshots yet — suggested spots to capture: the sidebar configuration panel, the live progress metrics during a run, and the Pareto Front tab._

## Tech Stack

| Layer | Technology |
|---|---|
| UI | [Streamlit](https://streamlit.io/) |
| Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) (`StateGraph`, `InMemorySaver` checkpointer, `interrupt_before`) |
| LLM client | [LangChain](https://python.langchain.com/) + `langchain_openai.ChatOpenAI` / `OpenAIEmbeddings` |
| LLM backend | Any OpenAI-compatible API, configured via `OPENAI_API_KEY` / `OPENAI_BASE_URL` |
| Env loading | `python-dotenv` (optional `.env`, never overrides real environment variables) |
| Package management | [uv](https://docs.astral.sh/uv/) |
| Language | Python ≥ 3.13 |

## Project Structure

```
Self-Improving Prompt Optimizer/
├── app.py                    # Streamlit UI — sidebar config, run driver, results tabs
├── graph.py                  # LangGraph workflow: state schema + the 7 optimization nodes
├── evaluator.py               # ChatOpenAI execution, LLM-as-judge scoring, embeddings
├── benchmark.py               # Fixed benchmark + LLM-based benchmark auto-generation
├── prompts.py                 # Default base prompt + every meta-prompt template
├── utils.py                    # Pure-stdlib helpers: cosine similarity, Pareto front, weighted score
├── run_app.cmd                 # One-click Windows launcher (uv sync + streamlit run)
├── pyproject.toml / uv.lock     # Dependency manifest (uv-managed)
├── .env.example                 # Template for OPENAI_API_KEY / OPENAI_BASE_URL
├── .gitignore
└── data/
    └── generated_benchmark.json  # Created on first "Generate Benchmark" click
```

## Installation & Setup

**Requirements:** Python 3.13+, [uv](https://docs.astral.sh/uv/), and access to an OpenAI-compatible API.

```bash
git clone https://github.com/pypi-ahmad/self-improving-prompt-optimizer.git
cd self-improving-prompt-optimizer
```

### Windows — one click

Double-click **`run_app.cmd`**. It checks for `uv`, warns if `OPENAI_API_KEY` isn't set, runs `uv sync` to install/update dependencies, then launches the app.

### Manual (any OS)

```bash
uv sync
uv run streamlit run app.py
```

Streamlit will open the app at `http://localhost:8531` (port set in `.streamlit/config.toml`).

## Environment Variables

The app reads these directly from the environment (`evaluator.py`, `app.py`):

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | API key for your OpenAI-compatible endpoint. The app refuses to start without it. |
| `OPENAI_BASE_URL` | No | Base URL of the endpoint (e.g. an enterprise gateway or proxy). Falls back to the client's default (`https://api.openai.com/v1`) if unset. |
| `AGNES_API_KEY` | No | Enables `agnes-2.5-flash` ([Agnes AI](https://www.agnes-ai.com/en/docs/overview), OpenAI-compatible, free tier) as a selectable model. Only used when that model is picked. |

Two ways to set them:

1. **System environment variables** (recommended if you already have them set) — the app uses these automatically, no extra step needed.
2. **`.env` file** — copy `.env.example` to `.env` and fill in your values. Loaded via `python-dotenv`, but a variable already present in the system environment always takes priority over `.env`.

## Usage

1. Launch the app (`run_app.cmd` or `uv run streamlit run app.py`).
2. In the sidebar, set the **base prompt**, **task description**, model/temperature, population size, number of generations, mutation strength, metric weights, selection strategy, diversity threshold, and benchmark source.
3. Click **Start Optimization**.
4. Watch live metrics (generation, best score, elite size, Pareto front size) and the log expander as each generation runs.
5. Optionally: check **Run continuously** to auto-advance generations, click **Run next generation** to step manually, type a prompt into the injection box and click **Inject** to seed it into the next generation, or click **Stop** to halt the run (progress is preserved; click **Resume** to continue).
6. When finished, inspect the **Best Prompt**, **Pareto Front**, and **History** tabs, and download results.

## How It Works

### The optimization loop (`graph.py`)

```
START → initialize_population
           │
           ▼
    ┌─► generate_variations   (elitism + LLM mutation/crossover + injected prompts)
    │      │
    │      ▼
    │  filter_by_diversity     (reject candidates too similar to existing elites, by embedding cosine similarity)
    │      │
    │      ▼
    │  evaluate_batch          (run each candidate on the benchmark, LLM-as-judge scores it, cache hits skip re-scoring)
    │      │
    │      ▼
    │  multi_objective_selection  (merge into elite pool, compute Pareto front, rank by weighted score)
    │      │
    │      ▼
    │  update_elite            (commit new elite set, track best prompt/score)
    │      │
    │      ▼
    │  check_stopping_condition  (max generations reached, or best score plateaued for 3 generations)
    │      │
    └──────┴─── continue ──────┘         stop → END
```

The graph is compiled with an `InMemorySaver` checkpointer and `interrupt_before=["generate_variations"]`, so it automatically pauses right before each new generation starts. `app.py` drives it with `graph.invoke(None, config)` — one call resolves exactly one generation — which is what makes **Stop** and **mid-run injection** possible without any background threads: the app simply chooses when (or whether) to call `invoke` again.

### Scoring

For each candidate prompt, `evaluator.py` runs it as a system prompt against every benchmark case, then asks the LLM to judge the output on `accuracy`, `clarity`, `conciseness`, and `helpfulness` (1–10 each). `consistency` is *not* judged directly — it's computed from the standard deviation of per-case scores, so a prompt that performs unevenly across inputs is penalized. A weighted score is then computed from the five metrics using the sidebar's weight sliders (normalized to sum to 1).

### Diversity filtering

Every candidate prompt is embedded with `OpenAIEmbeddings`. If its cosine similarity to any existing elite (or another candidate already accepted this generation) exceeds the diversity threshold, it's rejected as a near-duplicate — unless that would empty the whole generation, in which case one candidate is kept anyway. If the embeddings endpoint is unavailable, the filter is skipped gracefully rather than failing the run.

### Selection strategies

- **Weighted Score** — keep the top-N candidates by weighted score.
- **Pareto Front** — keep only non-dominated candidates (no other candidate scores at least as well on every metric and strictly better on at least one).
- **Hybrid** (default) — union of the Pareto front and the top-weighted candidates, capped at the population size.

## Configuration Options

| Sidebar control | Effect |
|---|---|
| Base prompt | The seed prompt for generation 1. |
| Task description | Used to steer mutation/crossover and (optionally) auto-generate a benchmark. |
| Model | Any chat model exposed by your endpoint's `/models` list (fine-tuned deployments are filtered out of the dropdown). |
| Temperature | Passed to `ChatOpenAI` for both candidate execution and judging. |
| Population size | Target number of candidates per generation; also the elite pool cap. |
| Number of generations | Hard stop on generation count. |
| Mutation strength | `low` / `medium` / `high` — how much the mutation prompt is told to change the seed. |
| Metric weights (×5) | Relative importance of each metric in the weighted score; recomputed live. |
| Selection strategy | `Weighted Score` / `Pareto Front` / `Hybrid`. |
| Diversity threshold | Max allowed cosine similarity before a candidate is rejected as a duplicate. |
| Benchmark source | `Built-in` (8 fixed cases) or `Auto-generated` (LLM-designed, persisted to disk). |

## Examples

**Default task:** _"Improve the following user message to be more professional, clear, and actionable."_

**Sample benchmark case** (`benchmark.py`):

```json
{
  "input": "hey can u send me the report by tmrw morning, need it for the meeting thx",
  "guideline": "Should read as a professional, clear, actionable request with a concrete deadline; casual abbreviations removed."
}
```

**Sample history row** (as exported to CSV/JSON):

```json
{
  "generation": 2,
  "source": "mutation",
  "prompt": "You are a professional editor tasked with enhancing the user's message...",
  "weighted_score": 8.58,
  "accuracy": 9.5,
  "clarity": 9.0,
  "conciseness": 9.0,
  "helpfulness": 8.0,
  "consistency": 7.38
}
```

To retarget the app at a different task entirely, edit `DEFAULT_BASE_PROMPT` / `DEFAULT_TASK_DESCRIPTION` in `prompts.py` and `DEFAULT_BENCHMARK` in `benchmark.py` — or just use the "Auto-generated" benchmark mode with a new task description.

## Future Improvements

- Expose the elite pool cap as its own sidebar control (currently fixed to population size).
- Optional toggle to surface fine-tuned/dated model deployments in the model dropdown (hidden by default).
- A non-Streamlit CLI entry point for headless/batch runs.
- Containerization (Dockerfile) for deployment outside a local machine.

## License

No license file is currently included. Add a `LICENSE` (e.g. MIT, Apache-2.0) if you intend to share or open-source this project.

## Acknowledgements

Built on [Streamlit](https://streamlit.io/), [LangGraph](https://github.com/langchain-ai/langgraph), [LangChain](https://python.langchain.com/), and the OpenAI-compatible chat/embeddings API.

<p align="center">Made with ❤️ by Ahmad Mujtaba</p>
