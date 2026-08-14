"""Streamlit UI for the self-improving prompt optimizer.

Drives graph.py one generation at a time: the compiled LangGraph pauses
(via `interrupt_before=["generate_variations"]`) right before each new
generation, which is exactly where this app wants to show progress and let
the user inject a prompt or stop before continuing.
"""

import csv
import io
import json
import os
import time

import streamlit as st
from dotenv import load_dotenv

# Loads .env if present, but never overrides a variable already set in the
# environment — on a machine where OPENAI_API_KEY/OPENAI_BASE_URL are already
# set (e.g. via Windows user env vars), those win; .env is only a fallback
# for other machines that haven't set them.
load_dotenv()

from benchmark import DEFAULT_BENCHMARK, generate_benchmark, load_benchmark, save_benchmark
from evaluator import ALL_METRICS, build_llm, list_available_models
from graph import build_graph, new_thread_config
from prompts import DEFAULT_BASE_PROMPT, DEFAULT_TASK_DESCRIPTION

STRATEGY_LABELS = {"Hybrid (default)": "hybrid", "Weighted Score": "weighted", "Pareto Front": "pareto"}

st.set_page_config(page_title="Self-Improving Prompt Optimizer", layout="wide")

if not os.environ.get("OPENAI_API_KEY"):
    st.error(
        "OPENAI_API_KEY is not set. Copy `.env.example` to `.env` and fill it in, "
        "or set OPENAI_API_KEY/OPENAI_BASE_URL as environment variables, then restart."
    )
    st.stop()


@st.cache_resource
def get_graph():
    return build_graph()


@st.cache_resource
def get_model_options():
    try:
        return list_available_models()
    except Exception:
        return ["gpt-4o-mini", "gpt-4o"]


def init_session_state():
    defaults = {
        "config": None,
        "state": None,
        "finished": False,
        "stopped": False,
        "error": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def run_one_generation(graph):
    try:
        result = graph.invoke(None, st.session_state.config)
    except Exception as exc:
        st.session_state.error = str(exc)
        st.session_state.stopped = True
        return
    st.session_state.state = result
    st.session_state.finished = len(graph.get_state(st.session_state.config).next) == 0


def render_sidebar():
    st.sidebar.header("Configuration")
    base_prompt = st.sidebar.text_area("Base prompt", DEFAULT_BASE_PROMPT, height=160, key="base_prompt")
    task_description = st.sidebar.text_area(
        "Task description (used for auto-benchmark generation)",
        DEFAULT_TASK_DESCRIPTION,
        height=70,
        key="task_description",
    )

    st.sidebar.divider()
    model_options = get_model_options()
    model_name = st.sidebar.selectbox("Model", model_options, index=0, key="model_name")
    temperature = st.sidebar.slider("Temperature", 0.0, 2.0, 0.7, 0.1, key="temperature")

    st.sidebar.divider()
    population_size = st.sidebar.number_input("Population size", 2, 20, 6, key="population_size")
    max_generations = st.sidebar.number_input("Number of generations", 1, 30, 5, key="max_generations")
    mutation_strength = st.sidebar.selectbox("Mutation strength", ["low", "medium", "high"], index=1, key="mutation_strength")

    st.sidebar.divider()
    st.sidebar.caption("Metric weights")
    weights = {
        "accuracy": st.sidebar.slider("Accuracy / Faithfulness", 0.0, 2.0, 1.0, 0.1, key="w_accuracy"),
        "clarity": st.sidebar.slider("Clarity", 0.0, 2.0, 1.0, 0.1, key="w_clarity"),
        "conciseness": st.sidebar.slider("Conciseness", 0.0, 2.0, 1.0, 0.1, key="w_conciseness"),
        "helpfulness": st.sidebar.slider("Helpfulness", 0.0, 2.0, 1.0, 0.1, key="w_helpfulness"),
        "consistency": st.sidebar.slider("Consistency", 0.0, 2.0, 1.0, 0.1, key="w_consistency"),
    }

    st.sidebar.divider()
    strategy_label = st.sidebar.radio("Selection strategy", list(STRATEGY_LABELS), index=0, key="strategy")
    diversity_threshold = st.sidebar.slider(
        "Diversity threshold (max cosine similarity)", 0.5, 0.99, 0.92, 0.01, key="diversity_threshold"
    )

    st.sidebar.divider()
    st.sidebar.caption("Benchmark")
    benchmark_mode = st.sidebar.radio("Benchmark source", ["Built-in", "Auto-generated"], index=0, key="benchmark_mode")
    if benchmark_mode == "Auto-generated":
        if st.sidebar.button("Generate benchmark from task description"):
            with st.sidebar.status("Generating benchmark...", expanded=False):
                try:
                    llm = build_llm(model_name, temperature)
                    cases = generate_benchmark(llm, task_description)
                    save_benchmark(cases)
                    st.sidebar.success(f"Generated and saved {len(cases)} test cases.")
                except Exception as exc:
                    st.sidebar.error(f"Benchmark generation failed: {exc}")

    return {
        "base_prompt": base_prompt,
        "task_description": task_description,
        "model_name": model_name,
        "temperature": temperature,
        "population_size": population_size,
        "max_generations": max_generations,
        "mutation_strength": mutation_strength,
        "metric_weights": weights,
        "selection_strategy": STRATEGY_LABELS[strategy_label],
        "diversity_threshold": diversity_threshold,
        "use_generated_benchmark": benchmark_mode == "Auto-generated",
    }


def render_progress(state):
    generation = state.get("generation", 0)
    max_generations = state.get("max_generations", 0)
    cols = st.columns(4)
    cols[0].metric("Generation", f"{generation} / {max_generations}")
    cols[1].metric("Best weighted score", f"{state.get('best_score', 0):.2f}" if state.get("best_score", -1) >= 0 else "-")
    cols[2].metric("Elite size", len(state.get("elite", [])))
    cols[3].metric("Pareto front size", len(state.get("pareto_front", [])))

    with st.expander("Logs", expanded=False):
        st.text("\n".join(state.get("logs", [])[-60:]) or "No logs yet.")


def render_pareto_front(state):
    front = state.get("pareto_front", [])
    if not front:
        st.info("No Pareto front yet — run at least one generation.")
        return
    rows = [
        {
            "prompt_preview": c["prompt"][:80] + ("..." if len(c["prompt"]) > 80 else ""),
            "weighted_score": round(c["weighted_score"], 2),
            **{k: round(c["metrics"][k], 2) for k in ALL_METRICS},
        }
        for c in sorted(front, key=lambda c: c["weighted_score"], reverse=True)
    ]
    st.dataframe(rows, use_container_width=True)


def render_best_prompt(state):
    best_prompt = state.get("best_prompt", "")
    best_metrics = state.get("best_metrics", {})
    st.subheader("Best prompt")
    st.text_area("best_prompt_display", best_prompt, height=160, disabled=True, label_visibility="collapsed")

    if best_metrics:
        cols = st.columns(len(ALL_METRICS))
        for col, metric in zip(cols, ALL_METRICS):
            col.metric(metric.capitalize(), f"{best_metrics.get(metric, 0):.2f}")
        st.bar_chart({m: best_metrics.get(m, 0) for m in ALL_METRICS})

    st.download_button("Download best prompt (.txt)", best_prompt, file_name="best_prompt.txt")


def render_history(state):
    history = state.get("history", [])
    if not history:
        st.info("No history yet — run at least one generation.")
        return
    st.dataframe(history, use_container_width=True)

    prompts_in_history = [row["prompt"] for row in history]
    chosen = st.selectbox("Inspect a prompt's per-test-case detail", prompts_in_history, key="history_inspect")
    if chosen:
        cached = state.get("score_cache", {}).get(chosen)
        if cached:
            st.dataframe(cached["per_case"], use_container_width=True)

    history_json = json.dumps(history, indent=2)
    buf = io.StringIO()
    if history:
        writer = csv.DictWriter(buf, fieldnames=list(history[0].keys()))
        writer.writeheader()
        writer.writerows(history)

    col1, col2 = st.columns(2)
    col1.download_button("Download full history (.json)", history_json, file_name="history.json")
    col2.download_button("Download full history (.csv)", buf.getvalue(), file_name="history.csv")


def main():
    init_session_state()
    graph = get_graph()
    config = render_sidebar()

    st.title("Self-Improving Prompt Optimizer")
    st.caption("Multi-objective evolution of a prompt against a fixed benchmark, judged by an LLM.")

    top = st.columns([1, 1, 4])
    start_clicked = top[0].button("Start Optimization", type="primary")
    stop_clicked = top[1].button("Stop", disabled=st.session_state.state is None or st.session_state.finished)

    if start_clicked:
        benchmark = load_benchmark(config["use_generated_benchmark"]) or DEFAULT_BENCHMARK
        thread_config = new_thread_config()
        initial_state = {
            "task_description": config["task_description"],
            "base_prompt": config["base_prompt"],
            "benchmark": benchmark,
            "model_name": config["model_name"],
            "temperature": config["temperature"],
            "population_size": config["population_size"],
            "max_generations": config["max_generations"],
            "mutation_strength": config["mutation_strength"],
            "metric_weights": config["metric_weights"],
            "selection_strategy": config["selection_strategy"],
            "diversity_threshold": config["diversity_threshold"],
        }
        try:
            result = graph.invoke(initial_state, thread_config)
            st.session_state.config = thread_config
            st.session_state.state = result
            st.session_state.finished = False
            st.session_state.stopped = False
            st.session_state.error = None
        except Exception as exc:
            st.session_state.error = str(exc)
        st.rerun()

    if stop_clicked:
        st.session_state.stopped = True

    if st.session_state.error:
        st.error(f"Error: {st.session_state.error}")

    state = st.session_state.state
    if state is None:
        st.info("Configure the run in the sidebar, then click **Start Optimization**.")
        return

    render_progress(state)

    if not st.session_state.finished:
        if st.session_state.stopped:
            st.warning(f"Stopped after generation {state.get('generation', 0)}.")
            if st.button("Resume"):
                st.session_state.stopped = False
                st.rerun()
        else:
            inject_col, button_col = st.columns([4, 1])
            inject_text = inject_col.text_input("Inject a custom prompt into the next generation", key="inject_text")
            if button_col.button("Inject") and inject_text.strip():
                try:
                    current = st.session_state.state.get("pending_injections", [])
                    graph.update_state(st.session_state.config, {"pending_injections": current + [inject_text.strip()]})
                    st.toast("Queued for the next generation.")
                except Exception as exc:
                    st.warning(f"Could not inject prompt: {exc}")

            auto_run = st.checkbox("Run continuously", value=True, key="auto_run")
            run_next = st.button("Run next generation", disabled=auto_run)

            if run_next:
                with st.spinner("Running generation..."):
                    run_one_generation(graph)
                st.rerun()
            elif auto_run:
                with st.spinner(f"Running generation {state.get('generation', 0) + 1}..."):
                    run_one_generation(graph)
                if not st.session_state.finished and not st.session_state.stopped:
                    time.sleep(0.2)
                st.rerun()
    else:
        st.success(f"Finished: {state.get('stop_reason', 'done')}")

    st.divider()
    tab1, tab2, tab3 = st.tabs(["Best Prompt", "Pareto Front", "History"])
    with tab1:
        render_best_prompt(state)
    with tab2:
        render_pareto_front(state)
    with tab3:
        render_history(state)


if __name__ == "__main__":
    main()
