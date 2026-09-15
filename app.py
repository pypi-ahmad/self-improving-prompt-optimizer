"""Streamlit controls for portable prompt optimization and bounded validation."""

import copy
import json
import os

import streamlit as st
from dotenv import load_dotenv

from benchmark import (
    builtin_benchmark,
    generate_benchmark,
    load_benchmark,
    save_benchmark,
    validate_benchmark,
)
from contracts import METRICS, guidance_snapshot, make_contract, parse_json
from graph import build_graph, make_initial_state, new_thread_config
from prompts import DEFAULT_BASE_PROMPT, DEFAULT_TASK_DESCRIPTION
from reporting import export_run, history_csv, history_rows
from runtime import LUNA, PRICES, TERRA, Runtime, default_models, safe_error

load_dotenv()
st.set_page_config(page_title="Self-Improving Prompt Optimizer", layout="wide")

HELP_CONTENT = {
    "getting_started": (
        "How to use this app",
        """This app tests and improves the instructions you give to an AI.

1. **Define the task.** Describe what the AI should do in **Task description** and
   put your existing instructions in **Base prompt**. For a first run, keep the example.
2. **Choose test cases.** Use **Built-in** for the supplied message-rewriting task.
   For another task, choose **Generate** or **Import JSON**.
3. **Check your allowance and start.** Review the models and **USD allowance**, then
   click **Start Optimization**. The default $6 allowance is a ceiling, not a fixed fee.
   **Prepare benchmark** is optional: it lets you inspect the cases first and may make paid API calls.
4. **Follow the run.** Let it run automatically, or turn off **Run continuously** and
   use **Run next stage**. **Stop** pauses between stages; **Resume** continues.
5. **Review the recommendation.** When finished, open **Comparison** and download
   the recommended prompt. A higher search score alone does not establish improvement.

Settings freeze when preparation starts. Download anything you want to keep before
**New run**, which discards the current run and permits a fresh allowance.

If you see an **OPENAI_API_KEY** error, configure the key in the server environment
or an existing `.env` file before starting. Do not put API keys in your prompt.""",
    ),
    "configuration": (
        "Configuration help",
        """- **Task description:** what the AI should accomplish.
- **Base prompt:** the instructions you want to improve, not a test input.
- **Required constraints:** rules every revision must preserve.
- **Protected prompt literals:** exact strings already in the base prompt that must stay unchanged.

The **Generation model** writes revisions; the **Candidate model** tries them on
test inputs; the **Judge model** scores the responses.

For a first run, keep the defaults. The **USD allowance** limits estimated spending;
you pay for usage, not the entire allowance. Prices must match your provider.""",
    ),
    "benchmark": (
        "Benchmark help",
        """A benchmark is a collection of test inputs and guidelines for good responses.
**Optimization cases** guide improvements. Separate **holdout cases** check the
selected prompt on inputs that did not guide the search.

- **Built-in:** use with the default message-rewriting task.
- **Generate:** create cases for your task; this uses the run's allowance.
- **Import JSON:** upload your own cases and optional checks.
- **Saved generated:** reuse a saved benchmark matching this task and prompt.

Use **Prepare benchmark** and **Download benchmark (.json)** to inspect cases before starting.""",
    ),
    "controls": (
        "Run controls help",
        """- **Prepare benchmark:** get cases ready and freeze settings; generation can incur costs.
- **Start Optimization:** prepare if needed, then test the original prompt and begin searching.
- **Run continuously:** advance automatically; turn it off for **Run next stage**.
- **Stop / Resume:** pause between stages and continue the same run. In-flight requests finish first.
- **Inject:** queue another prompt for the next generation; extra prompts wait for free slots.
- **New run:** discard current results and unlock settings for a fresh allowance.

Download results before starting over. Merely opening this help does not make API calls.""",
    ),
    "results": (
        "Results help",
        """- **Best Prompt:** the strongest search result; it may not be the final recommendation.
- **Comparison:** the final recommendation, side-by-side outputs, and cases that became worse.
- **Pareto Front:** candidates with different quality tradeoffs; none is beaten on every measure.
- **History:** evaluated prompts, scores, checks, and failures.

The **baseline** is your original prompt. Incomplete validation or no qualifying
improvement keeps the baseline recommendation. Read the comparison before adopting a revision.

Download a prompt as text, history as JSON/CSV, or the complete run as JSON. Downloads
cannot resume a run after the server restarts.""",
    ),
}


def render_help(topic):
    title, body = HELP_CONTENT[topic]
    with st.popover("ⓘ", type="tertiary", help=title, key=f"help_{topic}", on_change="ignore"):
        st.markdown(f"### {title}")
        st.markdown(body)


def init_session_state():
    for key, value in {
        "runtime": None,
        "frozen": None,
        "graph": None,
        "state": None,
        "config": None,
        "bundle": None,
        "stopped": False,
        "error": None,
    }.items():
        st.session_state.setdefault(key, value)


def render_sidebar():
    locked = st.session_state.runtime is not None
    with st.sidebar.container(horizontal=True, vertical_alignment="center"):
        st.header("Configuration", width="stretch")
        render_help("configuration")
    if locked:
        st.sidebar.caption("Settings are frozen. New run creates a new allowance.")
    task = st.sidebar.text_area("Task description", DEFAULT_TASK_DESCRIPTION, key="task", disabled=locked)
    base = st.sidebar.text_area(
        "Base prompt", DEFAULT_BASE_PROMPT, height=150, key="base_prompt", disabled=locked
    )
    constraints = st.sidebar.text_area(
        "Required constraints",
        key="constraints",
        disabled=locked,
        help="Requirements that every rewritten prompt must preserve.",
    )
    literals = st.sidebar.text_area(
        "Protected prompt literals (one per line)",
        key="literals",
        disabled=locked,
        help="Exact strings already in the base prompt. Output checks belong in the benchmark.",
    )
    models = default_models()
    with st.sidebar.expander("Models and reasoning", expanded=True):
        for role, default in (("generation", LUNA), ("candidate", LUNA), ("judge", TERRA)):
            models[role]["model"] = st.text_input(
                f"{role.capitalize()} model", default, key=f"model_{role}", disabled=locked
            )
            effort = st.selectbox(
                f"{role.capitalize()} reasoning",
                ["medium", "low", "high", "none", "omit"],
                key=f"effort_{role}",
                disabled=locked,
            )
            models[role]["reasoning_effort"] = None if effort == "omit" else effort
            if models[role]["model"] not in {LUNA, TERRA}:
                temp = st.number_input(
                    f"{role.capitalize()} temperature (-1 to omit)",
                    -1.0,
                    2.0,
                    -1.0,
                    key=f"temp_{role}",
                    disabled=locked,
                )
                models[role]["temperature"] = None if temp < 0 else temp
    with st.sidebar.expander("Search settings"):
        population = st.number_input("Population size", 2, 20, 6, key="population", disabled=locked)
        generations = st.number_input("Number of generations", 1, 30, 5, key="generations", disabled=locked)
        strength = st.selectbox(
            "Mutation strength", ["low", "medium", "high"], index=1, key="strength", disabled=locked
        )
        strategy = st.selectbox(
            "Selection strategy", ["hybrid", "weighted", "pareto"], key="strategy", disabled=locked
        )
        threshold = st.slider("Maximum cosine similarity", 0.5, 0.99, 0.92, key="threshold", disabled=locked)
        weights = {
            metric: st.slider(metric.capitalize(), 0.0, 2.0, 1.0, 0.1, key=f"w_{metric}", disabled=locked)
            for metric in METRICS
        }
        st.caption("Consistency is diagnostic only. Finalists and holdout outputs are evaluated twice.")
    with st.sidebar.expander("Budget and concurrency", expanded=True):
        usd = st.number_input("USD allowance", 0.01, 1000.0, 6.0, key="usd_cap", disabled=locked)
        calls = st.number_input("Maximum API attempts", 1, 10000, 1000, key="call_cap", disabled=locked)
        concurrency = st.number_input("Concurrent requests", 1, 8, 4, key="concurrency", disabled=locked)
        price_rows = st.data_editor(
            [{"model": name, **prices} for name, prices in PRICES.items()],
            num_rows="dynamic",
            key="prices",
            disabled=locked,
        )
        st.caption(
            "Prices are USD per 1M tokens. Add a price row for custom or embedding models. Unpriced embeddings are skipped."
        )
    with st.sidebar.container(horizontal=True, vertical_alignment="center"):
        st.markdown("**Benchmark**", width="stretch")
        render_help("benchmark")
    mode = st.sidebar.radio(
        "Benchmark source",
        ["Built-in", "Generate", "Import JSON", "Saved generated"],
        key="benchmark_mode",
        disabled=locked,
    )
    uploaded = None
    if mode == "Import JSON":
        uploaded = st.sidebar.file_uploader(
            "Benchmark JSON", type="json", key="benchmark_upload", disabled=locked
        )
    return {
        "contract": make_contract(
            task, base, constraints, [line for line in literals.splitlines() if line.strip()]
        ),
        "models": models,
        "prices": {
            row["model"]: {k: row[k] for k in ("input", "cached_input", "output")}
            for row in price_rows
            if row.get("model")
        },
        "usd_cap": usd,
        "call_cap": calls,
        "concurrency": concurrency,
        "benchmark_mode": mode,
        "uploaded": uploaded.getvalue().decode("utf-8") if uploaded else None,
        "settings": {
            "population_size": population,
            "max_generations": generations,
            "mutation_strength": strength,
            "selection_strategy": strategy,
            "diversity_threshold": threshold,
            "metric_weights": weights,
        },
    }


def prepare(config):
    if st.session_state.runtime is None:
        snapshot = copy.deepcopy(config)
        snapshot["guidance"] = guidance_snapshot()
        runtime = Runtime(
            models=snapshot["models"],
            prices=snapshot["prices"],
            usd_cap=snapshot["usd_cap"],
            call_cap=snapshot["call_cap"],
            concurrency=snapshot["concurrency"],
        )
        st.session_state.runtime = runtime
        st.session_state.frozen = snapshot
    frozen = st.session_state.frozen
    if st.session_state.bundle is None:
        mode = frozen["benchmark_mode"]
        if mode == "Built-in":
            bundle = builtin_benchmark(frozen["contract"])
        elif mode == "Generate":
            bundle = generate_benchmark(st.session_state.runtime, frozen["contract"], frozen["guidance"])
            save_benchmark(bundle)
        elif mode == "Saved generated":
            bundle = load_benchmark(True, frozen["contract"])
        else:
            if not frozen["uploaded"]:
                raise ValueError("Choose a benchmark JSON file before starting.")
            bundle = validate_benchmark(parse_json(frozen["uploaded"]), frozen["contract"])
        st.session_state.bundle = bundle


def start_run(config):
    prepare(config)
    frozen = st.session_state.frozen
    initial = make_initial_state(
        frozen["contract"],
        st.session_state.bundle,
        frozen["guidance"],
        frozen["models"],
        **frozen["settings"],
    )
    graph = build_graph(st.session_state.runtime)
    thread = new_thread_config()
    st.session_state.graph = graph
    st.session_state.config = thread
    st.session_state.state = graph.invoke(initial, thread)
    st.session_state.stopped = False
    st.session_state.error = None


def run_one_stage():
    graph = st.session_state.graph
    thread = st.session_state.config
    if graph.get_state(thread).next:
        st.session_state.state = graph.invoke(None, thread)


def render_usage(runtime):
    usage = runtime.snapshot()
    cols = st.columns(4)
    cols[0].metric("API attempts", f"{usage['calls']} / {usage['call_cap']}")
    cols[1].metric("Accounted USD", f"${usage['charged_usd']:.4f}")
    cols[2].metric("Remaining allowance", f"${usage['remaining_usd']:.4f}")
    cols[3].metric("Elapsed", f"{usage['elapsed_seconds']:.1f}s")
    st.caption(
        f"Usage-based estimate: ${usage['reported_usd']:.4f}; reserved or unreported: ${usage['reserved_usd']:.4f}."
    )
    with st.expander("Usage by request, model, and phase"):
        st.dataframe(usage["by_model_phase"])
        st.dataframe(usage["events"])
        if usage["events"]:
            st.caption("Completion tokens include reasoning. Missing usage retains the full reservation.")
    if usage["halted"]:
        st.error("Reported usage exceeded its reservation. Further calls are disabled.")


def render_results(state):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader("Results", width="stretch")
        render_help("results")
    best, comparison, front, history = st.tabs(["Best Prompt", "Comparison", "Pareto Front", "History"])
    with best:
        st.subheader("Best optimization prompt")
        st.text_area("Best prompt", state["best_prompt"], height=160, disabled=True)
        if state["best_metrics"]:
            st.bar_chart(state["best_metrics"])
        st.download_button(
            "Download best prompt (.txt)", state["best_prompt"], "best_prompt.txt", on_click="ignore"
        )
        st.caption("The final recommendation appears in Comparison after validation.")
    with comparison:
        report = state.get("comparison")
        if not report:
            st.info("Finalist and holdout validation run after search finishes.")
        else:
            if report["status"] != "complete":
                st.warning("Validation incomplete. The baseline remains the recommendation.")
            elif report["improved"]:
                st.success("The selected prompt improved on these holdout cases.")
            else:
                st.info("No qualifying improvement established. Keep the baseline.")
            st.caption(report["note"])
            st.download_button(
                "Download recommended prompt",
                report["recommendation"],
                "recommended_prompt.txt",
                on_click="ignore",
            )
            st.dataframe(
                [
                    {
                        "prompt": r["prompt"],
                        "status": r["status"],
                        "eligible": r["eligible"],
                        "repeatability_stddev": r["repeatability"],
                        **(r["metrics"] or {}),
                    }
                    for r in state.get("finalists", [])
                ]
            )
            st.write("Holdout regressions")
            st.dataframe(report["regressions"])
            for left, right in zip(report["baseline"]["per_case"], report["candidate"]["per_case"]):
                with st.expander(f"{left['id']} · repeat {left['repeat'] + 1}"):
                    st.write(left["input"])
                    for col, label, row in zip(st.columns(2), ("Baseline", "Candidate"), (left, right)):
                        with col:
                            st.write(label)
                            st.text(row["output"])
                            st.write(
                                {"status": row["status"], "scores": row["scores"], "checks": row["checks"]}
                            )
                            st.caption(row["rationale"])
    with front:
        st.dataframe(
            [
                {"prompt": row["prompt"], "weighted_score": row["weighted_score"], **row["metrics"]}
                for row in state.get("pareto_front", [])
            ]
        )
    with history:
        st.dataframe(history_rows(state))
        records = state.get("history", [])
        if records:
            index = st.selectbox(
                "Inspect per-case detail",
                range(len(records)),
                format_func=lambda i: f"Generation {records[i]['generation']}: {records[i]['prompt'][:65]}",
            )
            st.dataframe(records[index]["per_case"])
        st.download_button(
            "Download full history (.json)", json.dumps(records, indent=2), "history.json", on_click="ignore"
        )
        st.download_button(
            "Download full history (.csv)", history_csv(state), "history.csv", on_click="ignore"
        )
    st.download_button(
        "Download complete run (.json)",
        export_run(state, st.session_state.runtime),
        "run.json",
        on_click="ignore",
    )


def main():
    init_session_state()
    with st.container(horizontal=True, vertical_alignment="center"):
        st.title("Self-Improving Prompt Optimizer", width="stretch")
        render_help("getting_started")
    st.caption("Evolve prompts, test unseen cases, and compare results within a fixed allowance.")
    if not os.environ.get("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY is not set. Configure it in the environment or existing .env file.")
        return
    try:
        config = render_sidebar()
    except (ValueError, KeyError, TypeError) as exc:
        st.error(f"Invalid configuration: {safe_error(exc)['type']}. Check the task and model prices.")
        return
    first, second, third, help_column = st.columns([1, 1, 1, 0.3], vertical_alignment="center")
    with help_column:
        render_help("controls")
    if first.button("New run", disabled=st.session_state.runtime is None):
        for key in ("runtime", "frozen", "graph", "state", "config", "bundle", "error"):
            st.session_state[key] = None
        st.session_state.stopped = False
        st.rerun()
    if second.button("Prepare benchmark", disabled=st.session_state.bundle is not None):
        try:
            with st.spinner("Preparing benchmark within the run allowance..."):
                prepare(config)
        except Exception as exc:  # noqa: BLE001 - UI boundary must retain the preparation ledger.
            st.session_state.error = f"Preparation failed ({safe_error(exc)['type']}). Check benchmark structure, task, and provider settings."
        st.rerun()
    if third.button("Start Optimization", type="primary", disabled=st.session_state.graph is not None):
        try:
            with st.spinner("Evaluating the baseline..."):
                start_run(config)
        except Exception as exc:  # noqa: BLE001 - retain completed provider accounting on start failure.
            st.session_state.error = (
                f"Start failed ({safe_error(exc)['type']}). Check the configuration and benchmark."
            )
        st.rerun()
    if st.session_state.error:
        st.error(st.session_state.error)
    if st.session_state.bundle:
        bundle = st.session_state.bundle
        st.caption(
            f"Benchmark: {len(bundle['optimization'])} optimization cases and {len(bundle['holdout'])} holdout cases. Both skills are active."
        )
        st.download_button(
            "Download benchmark (.json)", json.dumps(bundle, indent=2), "benchmark.json", on_click="ignore"
        )
    if st.session_state.runtime:
        render_usage(st.session_state.runtime)
    state = st.session_state.state
    if not state:
        return
    st.subheader(
        f"{state['phase'].capitalize()} · generation {state['generation']} / {state['settings']['max_generations']}"
    )
    st.caption(f"Evaluation cache hits: {state['cache_hits']}")
    with st.expander("Logs"):
        st.text("\n".join(state.get("logs", [])[-60:]))
    render_results(state)
    if state["phase"] == "finished":
        st.write(f"Search stopped: {state['stop_reason']}.")
        return
    controls = st.columns(2)
    if controls[0].button("Stop", disabled=st.session_state.stopped):
        st.session_state.stopped = True
    if controls[1].button("Resume", disabled=not st.session_state.stopped):
        st.session_state.stopped = False
    if state["phase"] == "search":
        injection = st.text_input("Inject a prompt into the next generation", key="injection")
        if st.button("Inject") and injection.strip():
            graph = st.session_state.graph
            current = graph.get_state(st.session_state.config).values
            graph.update_state(
                st.session_state.config,
                {"pending_injections": current.get("pending_injections", []) + [injection]},
            )
            st.session_state.state = graph.get_state(st.session_state.config).values
            st.toast("Prompt queued.")
    auto = st.checkbox("Run continuously", value=True, key="auto_run")
    next_clicked = st.button("Run next stage", disabled=st.session_state.stopped or auto)
    st.caption("Stop and Resume take effect between generations and validation stages.")
    if not st.session_state.stopped and (auto or next_clicked):
        try:
            with st.spinner("Running stage..."):
                run_one_stage()
        except Exception as exc:  # noqa: BLE001 - pause with the last completed checkpoint intact.
            st.session_state.error = (
                f"Stage failed ({safe_error(exc)['type']}). Completed checkpoints are retained."
            )
            st.session_state.stopped = True
        st.rerun()


if __name__ == "__main__":
    main()
