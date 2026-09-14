# Technical details

This document covers the technology stack, module implementations, operational invariants, error handling strategies, and data persistence paths for Self-Improving Prompt Optimizer.

## Technology stack

| Library / Tool | Version Constraint | Direct Usage in Codebase |
|---|---|---|
| Python | `>=3.13` | Specified in `pyproject.toml` and `.python-version`. |
| Streamlit | `>=1.61.1` | Used in `app.py` for web UI layout, parameter controls, caching (`@st.cache_resource`), session state management, and file export widgets. |
| LangGraph | `>=1.2.11` | Used in `graph.py` (`StateGraph`, `InMemorySaver`, `START`, `END`) to construct the cyclic optimization state machine and manage pause/resume execution. |
| LangChain | `>=1.3.15` | Core foundation for model abstractions. |
| LangChain-OpenAI | `>=1.5.0` | Used in `evaluator.py` (`ChatOpenAI`, `OpenAIEmbeddings`) to interface with OpenAI-compatible chat and vector embedding endpoints. |
| OpenAI Python SDK | Transitive dependency | Used in `evaluator.py` (`OpenAI`) for querying `client.models.list()` to populate available models. |
| python-dotenv | `>=1.2.2` | Used in `app.py` (`load_dotenv()`) to load `.env` files into environment variables without overriding existing process variables. |
| uv | Unpinned | Referenced in `run_app.cmd` and `pyproject.toml` as the project dependency and runtime manager. |

## Module responsibilities

- `app.py`:
  - Configures Streamlit page layout and sidebar widgets.
  - Maintains run session state (`st.session_state`).
  - Calls `get_graph()` and dispatches execution via `graph.invoke(None, config)` or `graph.invoke(initial_state, thread_config)`.
  - Allows human-in-the-loop interactions: Start, Stop, Resume, and prompt injection (`graph.update_state`).
  - Renders performance metrics, Pareto front tables, full evaluation history, and per-test-case drill-down tables.
  - Generates downloadable files (`best_prompt.txt`, `history.json`, `history.csv`).
- `graph.py`:
  - Defines the `OptimizerState` dictionary schema.
  - Implements the 7 optimization nodes: `initialize_population`, `generate_variations`, `filter_by_diversity`, `evaluate_batch`, `multi_objective_selection`, `update_elite`, and `check_stopping_condition`.
  - Configures conditional loop routing via `_route_after_stopping_check`.
  - Compiles the state graph with `InMemorySaver` and `interrupt_before=["generate_variations"]`.
- `evaluator.py`:
  - Dispatches credentials and base URLs based on model names via `_credentials_for()`.
  - Manages provider routing for default OpenAI-compatible endpoints and optional providers (Agnes AI).
  - Instantiates `ChatOpenAI` and `OpenAIEmbeddings`.
  - Executes candidate prompts against benchmark test cases.
  - Executes LLM-as-judge scoring requests using `JUDGE_PROMPT_TEMPLATE`.
  - Calculates the `consistency` metric from the standard deviation of per-case scores.
  - Generates vector embeddings for candidate diversity filtering.
  - Discovers chat models via `client.models.list()`, excluding models containing `:` (such as fine-tuned deployments).
- `benchmark.py`:
  - Defines `DEFAULT_BENCHMARK` (8 static test cases with inputs and guidelines).
  - Implements `load_benchmark()` to read `data/generated_benchmark.json` or fallback to defaults.
  - Implements `save_benchmark()` to persist generated test cases to disk.
  - Implements `generate_benchmark()` to query an LLM for novel test cases from a task description.
- `prompts.py`:
  - Contains default task strings: `DEFAULT_TASK_DESCRIPTION` and `DEFAULT_BASE_PROMPT`.
  - Defines metric constants: `METRIC_NAMES` (`accuracy`, `clarity`, `conciseness`, `helpfulness`, `consistency`).
  - Defines meta-prompt templates: `MUTATION_PROMPT_TEMPLATE`, `CROSSOVER_PROMPT_TEMPLATE`, `JUDGE_PROMPT_TEMPLATE`, and `BENCHMARK_GENERATION_PROMPT_TEMPLATE`.
  - All prompt templates mandate strict JSON-only outputs.
- `utils.py`:
  - Pure standard-library utility module with no third-party imports.
  - `strip_json_fence(text)`: Removes markdown code block delimiters (` ```json ` or ` ``` `).
  - `cosine_similarity(a, b)`: Calculates vector cosine similarity.
  - `max_similarity(embedding, others)`: Finds maximum cosine similarity between a vector and a collection of vectors.
  - `normalized_weights(weights)`: Normalizes metric weight dictionaries to sum to 1.0.
  - `weighted_score(metrics, weights)`: Computes dot product of normalized weights and metric scores.
  - `is_dominated(candidate, other, metric_keys)`: Evaluates Pareto dominance condition.
  - `pareto_front(candidates, metric_keys)`: Filters a candidate list to its non-dominated Pareto subset.
- `run_app.cmd`:
  - Windows batch script providing automated installation of `uv`, creation of `.env` from `.env.example`, execution of `uv sync`, and startup of Streamlit on port `8531`.

## Important invariants

1. **Strict JSON output contract**:
   All meta-prompts in `prompts.py` instruct LLMs to respond with raw JSON arrays or objects without prose or markdown fences. Callers apply `strip_json_fence()` before invoking `json.loads()`.
2. **Elitism**:
   All candidates present in `state["elite"]` are retained into the next generation's candidate pool without modification.
3. **Elite pool floor**:
   In `multi_objective_selection()`, the elite pool capacity is set to `max(population_size, 3)`. The pool maintains at least 3 candidates regardless of how low `population_size` is configured.
4. **Exact-match score caching**:
   Candidate evaluation results are cached in `state["score_cache"]` using the prompt text string as the dictionary key. Carried-forward elites hit the cache and bypass repeat model evaluations. Any variation in whitespace or character casing results in a cache miss.
5. **Diversity filter safety floor**:
   If every candidate in a generation is rejected because its cosine similarity to existing vectors exceeds `diversity_threshold`, `filter_by_diversity()` preserves the first candidate to ensure the population does not become empty.
6. **Multi-objective consistency metric**:
   Consistency is calculated deterministically from the spread of overall scores across all benchmark test cases:
   $$\text{consistency} = \max(0.0, 10.0 - 3.0 \times \text{pstdev}(\text{case scores}))$$
   If fewer than two test cases are evaluated, consistency defaults to `10.0`.
7. **Plateau convergence criteria**:
   In `check_stopping_condition()`, a run terminates early if the best score history contains at least 3 entries (`PLATEAU_WINDOW = 3`) and the difference between maximum and minimum best scores across that window is less than `0.05` (`PLATEAU_EPSILON = 0.05`).

## Error handling

| Subsystem / Operation | Failure Scenario | Handler Behavior |
|---|---|---|
| Startup check (`app.py`) | `OPENAI_API_KEY` is not present in environment or `.env` | Displays `st.error()` notification and terminates script execution via `st.stop()`. |
| Candidate generation (`graph.py`) | LLM call for mutation or crossover raises `Exception` | Catches `Exception`, logs failure message to state logs, and continues with remaining available candidates. |
| Diversity filtering (`evaluator.py`, `graph.py`) | `OpenAIEmbeddings.embed_documents()` raises `Exception` | Catches `Exception`, logs warning, and returns `None`. `filter_by_diversity()` skips filtering and retains all generated candidates. |
| Judge evaluation (`evaluator.py`) | Output generation for candidate fails | Logs failure message and records output as an empty string. |
| Judge evaluation (`evaluator.py`) | LLM judge output cannot be parsed as JSON or lacks metric keys | Catches `Exception`, logs failure, and assigns fallback score of `5.0` to each judged metric (`accuracy`, `clarity`, `conciseness`, `helpfulness`). |
| Model discovery (`evaluator.py`) | `client.models.list()` raises `Exception` | Catches `Exception` and falls back to `["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"]`. |
| Benchmark generation (`benchmark.py`) | Generated test cases fail validation (missing `input` or `guideline`) | Discards invalid test cases. If no valid cases remain, raises `ValueError`, which `app.py` displays in the sidebar. |
| Benchmark file read (`benchmark.py`) | `data/generated_benchmark.json` is missing or contains invalid JSON | Catches `(json.JSONDecodeError, OSError)` and falls back to `DEFAULT_BENCHMARK`. |
| Generation step execution (`app.py`) | `graph.invoke()` raises `Exception` | Catches `Exception`, stores error message in `st.session_state.error`, sets `st.session_state.stopped = True`, and renders an error banner. |

## Persistence paths

1. **Optimization state (in-memory only)**:
   - State graph checkpoints are held in memory using `langgraph.checkpoint.memory.InMemorySaver`.
   - Thread identifiers are generated using `uuid.uuid4()`.
   - Stopping the Python process or clicking "Start Optimization" starts a new thread, resetting all population, elite, and history data.
2. **Auto-generated benchmark (disk)**:
   - Written to `data/generated_benchmark.json` via `benchmark.save_benchmark()`.
   - Stored in standard unencrypted JSON format with 2-space indentation.
   - Overwritten wholesale whenever benchmark generation is triggered from the UI.
3. **User exports (browser download)**:
   - Best prompt text: Downloaded as `best_prompt.txt` via `st.download_button()`.
   - Full history: Downloaded as `history.json` or formatted table `history.csv` via `st.download_button()`.
