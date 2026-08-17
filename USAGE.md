# Usage Guide

A step-by-step walkthrough of the Streamlit app, grounded in the actual UI
code in `app.py`. For what the app is and how it's built, see
[ARCHITECTURE.md](ARCHITECTURE.md).

## 1. First-time setup

**Windows, one click:**

```powershell
run_app.cmd
```

This checks for `uv`, warns if `OPENAI_API_KEY` isn't set, runs `uv sync`,
and launches the app at `http://localhost:8531`.

**Manual, any OS:**

```bash
uv sync
cp .env.example .env    # then edit .env with your key
uv run streamlit run app.py
```

You need `OPENAI_API_KEY` set (the app refuses to start without it —
you'll see an error banner and a stopped app if it's missing). Optionally
set `OPENAI_BASE_URL` to point at a different OpenAI-compatible endpoint,
and `AGNES_API_KEY` to enable `agnes-2.5-flash` as a selectable model.

## 2. Configure a run (sidebar)

| Control | What it does |
|---|---|
| Base prompt | The seed prompt for generation 1 |
| Task description | Steers mutation/crossover; also the input to auto-benchmark generation |
| Model | Any chat model from your endpoint's `/models` list (fine-tuned deployments are hidden) |
| Temperature | Used for both candidate execution and judging |
| Population size | Target candidates per generation (2–20); also the elite pool floor |
| Number of generations | Hard stop on generation count (1–30) |
| Mutation strength | `low` / `medium` / `high` — how much each mutation is told to change the seed |
| Metric weights (×5) | Relative importance of accuracy/clarity/conciseness/helpfulness/consistency; recomputed live |
| Selection strategy | `Hybrid` (default) / `Weighted Score` / `Pareto Front` |
| Diversity threshold | Max cosine similarity before a candidate is rejected as a near-duplicate (0.5–0.99) |
| Benchmark source | `Built-in` (8 fixed cases) or `Auto-generated` |

If you pick **Auto-generated**, click **"Generate benchmark from task
description"** — this asks the LLM to design 7 test cases from your task
description and saves them to `data/generated_benchmark.json` for reuse
across runs.

## 3. Start the run

Click **Start Optimization**. The first generation runs immediately; after
that, the graph pauses before each new generation so the UI can show
progress and offer Stop/Inject:

- **Generation / Best weighted score / Elite size / Pareto front size** —
  four live metrics above a scrollable **Logs** expander.
- **Run continuously** (checked by default) auto-advances one generation
  after another with a short pause between them. Uncheck it and use **Run
  next generation** to step through manually.
- **Inject a custom prompt** — type a prompt and click **Inject** to queue
  it as a guaranteed candidate in the *next* generation (it still goes
  through diversity filtering and scoring like any other candidate).
- **Stop** — halts auto-advancing; the current elite/history is preserved.
  Click **Resume** to continue from where you left off.

The run ends automatically once the generation limit is reached, or the
best score has stayed within a ±0.05 band for 3 consecutive generations
(plateau detection).

## 4. Review results

Three tabs appear once at least one generation has run:

- **Best Prompt** — the current best-scoring prompt, its per-metric
  breakdown and bar chart, and a **Download best prompt (.txt)** button.
- **Pareto Front** — every non-dominated candidate found so far, sorted by
  weighted score, with its full metric breakdown.
- **History** — every candidate ever scored across every generation, with
  a dropdown to inspect any prompt's per-test-case detail (input, output,
  and scores for each benchmark case), plus **Download full history**
  buttons for `.json` and `.csv`.

## 5. Starting over vs. continuing

There is no "load a past run" feature — optimization state lives only in
memory for the current app session (see [ARCHITECTURE.md](ARCHITECTURE.md)'s
"No persistence" note). Clicking **Start Optimization** again always
begins a brand-new run with a fresh thread; if you want to keep exploring
the same run, use Stop/Resume, Inject, or "Run next generation" instead of
restarting.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Red error banner, app won't start | `OPENAI_API_KEY` is not set | Set it in `.env` or your shell environment, then restart |
| Model dropdown only shows `gpt-4o-mini`/`gpt-4o` | Your endpoint's `/models` list couldn't be fetched (network issue, wrong `OPENAI_BASE_URL`, or the endpoint doesn't expose `/models`) | Falls back gracefully; check `OPENAI_BASE_URL` if you expected a different model list |
| `agnes-2.5-flash` doesn't appear in the model dropdown | `AGNES_API_KEY` is not set | Set it in `.env` — it's the only thing gating that model's visibility |
| Log line: "judge parse failed... using neutral fallback scores" | The judge LLM's response wasn't valid JSON | The run continues with a neutral score (5.0) for that case rather than failing; check the log for the underlying parse error if it happens often |
| Log line: "embeddings unavailable... skipping diversity filter" | The embeddings endpoint failed or isn't available on your configured base URL | Diversity filtering is skipped for that generation only; the run itself is unaffected |
| A generation kept an obvious near-duplicate anyway | Every candidate that generation was a near-duplicate of an elite; the app never lets a generation go empty | Expected behavior — lower the diversity threshold or increase mutation strength if this happens often |
| Best score "stuck" and the run stops early | Plateau detection: best score stayed within ±0.05 for 3 generations | Expected behavior — increase `Number of generations`' effect by adjusting the base prompt, mutation strength, or metric weights before starting a new run |
| **Stop** button is grayed out | No run has started yet, or the run has already finished | Expected — Stop only applies to an in-progress run |
| **Inject** silently does nothing | The text box was empty, or a run isn't currently active | Type a non-empty prompt while a run is paused between generations |

## Resetting

There is no run history to delete — it's in-memory only and clears when
the app process restarts. To clear a saved auto-generated benchmark,
delete `data/generated_benchmark.json`. Delete `.venv` and re-run
`run_app.cmd` / `uv sync` to reset the Python environment.
