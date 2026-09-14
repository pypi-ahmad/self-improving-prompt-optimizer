# Runbook

This runbook describes operational procedures for starting, controlling, and troubleshooting Self-Improving Prompt Optimizer.

## Start and stop procedures

### Starting the server

#### Automated start (Windows)

Execute the launcher script from the repository root:

```cmd
run_app.cmd
```

The script will:
1. Verify `uv` is installed (and download it via PowerShell if missing).
2. Copy `.env.example` to `.env` if `.env` does not exist.
3. Check whether `OPENAI_API_KEY` is present.
4. Execute `uv sync` to install dependencies.
5. Launch the Streamlit application on port `8531`.

#### Manual start (any operating system)

1. Synchronize dependencies:
   ```bash
   uv sync
   ```
2. Ensure environment variables are set:
   ```bash
   # Copy example template if .env does not exist
   cp .env.example .env
   ```
   Edit `.env` to include your `OPENAI_API_KEY`.
3. Launch Streamlit:
   ```bash
   uv run streamlit run app.py
   ```

The application starts an HTTP server at `http://localhost:8531` (port configured in `.streamlit/config.toml`).

### Controlling an optimization run

1. **Start a run**:
   - Navigate to `http://localhost:8531` in your browser.
   - Adjust configuration parameters in the left sidebar.
   - Click **Start Optimization** in the main view.
   - Note: Clicking **Start Optimization** at any time resets the state and starts a new optimization run under a fresh thread identifier.
2. **Step through generations**:
   - **Continuous execution**: Keep **Run continuously** checked (default). Generations execute sequentially with a 200ms delay between iterations.
   - **Manual stepping**: Uncheck **Run continuously** and click **Run next generation** to advance one generation at a time.
3. **Mid-run prompt injection**:
   - While a run is paused or stepping manually, enter prompt text into the **Inject a custom prompt into the next generation** text box.
   - Click **Inject**. The prompt is appended to `state["pending_injections"]` and integrated during the next generation's variation stage.
4. **Pause or stop a run**:
   - Click **Stop**. The current generation completes its execution, and the state machine pauses before the subsequent `generate_variations` node.
   - Click **Resume** to continue execution from the paused state.
5. **Terminating the server**:
   - Press `Ctrl+C` in the terminal executing Streamlit, or close the terminal window.
   - Caution: Optimization state is held strictly in process memory. Terminating the process discards all active run history, Pareto front data, and the score cache.

## Logs location

- **Web interface**: An expandable container labeled **Logs** is displayed directly beneath the generation metrics on the main page (`app.py`). It renders the last 60 log lines from `state["logs"]`.
- **Terminal console**: Standard output (`stdout`) and standard error (`stderr`) streams print directly to the active terminal window running `streamlit run app.py` or `run_app.cmd`. No log files are written to disk.

## Diagnostic reference and common failures

### Missing API key on startup

- **Observed error**: `OPENAI_API_KEY is not set. Copy .env.example to .env and fill it in, or set OPENAI_API_KEY/OPENAI_BASE_URL as environment variables, then restart.`
- **Location**: `app.py`
- **Cause**: The application checked `os.environ.get("OPENAI_API_KEY")` and found no value.
- **Resolution**:
  - Add `OPENAI_API_KEY=your_key` to `.env` in the repository root.
  - Alternatively, export `OPENAI_API_KEY` in your system environment variables.
  - Restart the application.

### Dependency synchronization failure

- **Observed error**: `[ERROR] uv sync failed. See the output above.`
- **Location**: `run_app.cmd`
- **Cause**: `uv sync` returned a non-zero exit code due to network failure, package index unavailability, or an incompatible Python runtime.
- **Resolution**: Verify that Python `>=3.13` is available on the system PATH and that outgoing internet connections are functional.

### Benchmark generation failure

- **Observed error**: `Benchmark generation failed: <exception>`
- **Location**: Sidebar status container in `app.py`
- **Cause**: The model invocation in `benchmark.generate_benchmark()` failed, or the response could not be parsed as a JSON array of objects containing `input` and `guideline` keys.
- **Resolution**:
  - Verify API connectivity and rate limit quotas for the selected model.
  - Review the task description text in the sidebar to ensure it specifies a valid task.
  - Re-click **Generate benchmark from task description**.

### Neutral fallback scoring during evaluation

- **Observed log entry**: `judge parse failed (<exc>); using neutral fallback scores`
- **Location**: `evaluator.py`, displayed in UI logs expander
- **Cause**: The LLM response to `JUDGE_PROMPT_TEMPLATE` was malformed JSON or omitted one of the judged metric keys (`accuracy`, `clarity`, `conciseness`, `helpfulness`).
- **Impact**: The evaluator assigns `5.0` to each judged metric for the affected test case. The run does not halt.
- **Resolution**: If this occurs frequently, consider using a different model or lowering the temperature to reduce non-compliant JSON outputs.

### Diversity filter bypass

- **Observed log entry**: `embeddings unavailable (<exc>); skipping diversity filter this generation`
- **Location**: `evaluator.py`, displayed in UI logs expander
- **Cause**: The embedding client call to `OpenAIEmbeddings.embed_documents()` failed (endpoint does not support embeddings, model `text-embedding-3-small` is unavailable, or a network timeout occurred).
- **Impact**: Diversity filtering is bypassed for the current generation, and all generated candidates are passed to evaluation.
- **Resolution**: If diversity filtering is required, ensure the configured endpoint supports OpenAI-compatible embeddings and the `text-embedding-3-small` model.

### Near-duplicate forced retention

- **Observed log entry**: `every candidate was a near-duplicate; kept one anyway.`
- **Location**: `graph.py`, displayed in UI logs expander
- **Cause**: Every candidate generated in the batch exceeded `diversity_threshold` relative to existing elite vectors or batch candidates.
- **Impact**: One candidate is retained unconditionally to prevent an empty population.
- **Resolution**: Lower the **Diversity threshold** slider in the sidebar (for example, from `0.92` to `0.85`), or increase **Mutation strength** to encourage greater candidate variation.

### Run termination reasons

- **Observed log entry**: `Stopping check: STOP - reached max generations`
  - **Cause**: The generation counter reached `max_generations`.
  - **Resolution**: Expected completion. Increase **Number of generations** in the sidebar if additional iterations are desired.
- **Observed log entry**: `Stopping check: STOP - plateaued (best score flat for 3 generations)`
  - **Cause**: The maximum difference in best score over the previous 3 generations was less than `0.05`.
  - **Resolution**: Expected convergence. If further exploration is required, adjust metric weights, mutation strength, or the base prompt before starting a new run.

### Missing model in dropdown

- **Observed behavior**: `agnes-2.5-flash` does not appear in the model selection dropdown.
- **Location**: `evaluator.py`
- **Cause**: `AGNES_API_KEY` is not defined in the environment or `.env`.
- **Resolution**: Add `AGNES_API_KEY=your_key` to `.env` and restart the application.
