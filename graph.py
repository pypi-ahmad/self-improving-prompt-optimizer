"""LangGraph workflow: the cyclic multi-generation prompt-optimization loop.

initialize_population -> generate_variations -> filter_by_diversity ->
evaluate_batch -> multi_objective_selection -> update_elite ->
check_stopping_condition -> (loop back to generate_variations, or END)

Compiled with a checkpointer and `interrupt_before=["generate_variations"]` so
app.py can pause between generations to show progress, let the user inject a
prompt or stop, then resume with `graph.invoke(None, config)` — one call
advances exactly one generation.
"""

import json
import operator
import uuid
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

import evaluator
from prompts import CROSSOVER_PROMPT_TEMPLATE, MUTATION_PROMPT_TEMPLATE
from utils import max_similarity, pareto_front, strip_json_fence, weighted_score

PLATEAU_WINDOW = 3
PLATEAU_EPSILON = 0.05


class OptimizerState(TypedDict):
    # --- config: set once by app.py, read-only for the rest of the run ---
    task_description: str
    base_prompt: str
    benchmark: list[dict]
    model_name: str
    temperature: float
    population_size: int
    max_generations: int
    mutation_strength: str
    metric_weights: dict[str, float]
    selection_strategy: str  # "weighted" | "pareto" | "hybrid"
    diversity_threshold: float

    # --- evolving state ---
    generation: int
    population: list[dict]  # this gen's unscored candidates: [{"prompt", "source", "embedding"?}]
    evaluated: list[dict]  # this gen's scored candidates
    elite_candidates: list[dict]  # handoff: multi_objective_selection -> update_elite
    elite: list[dict]  # current elite pool (scored, deduped)
    pareto_front: list[dict]
    score_cache: dict[str, dict]  # prompt text -> {"metrics", "per_case"}, avoids re-scoring elites
    best_prompt: str
    best_score: float
    best_metrics: dict
    best_score_history: list[float]
    history: Annotated[list[dict], operator.add]
    pending_injections: list[str]
    should_stop: bool
    stop_reason: str
    logs: Annotated[list[str], operator.add]


def _llm(state: OptimizerState):
    return evaluator.build_llm(state["model_name"], state["temperature"])


def initialize_population(state: OptimizerState) -> dict:
    return {
        "generation": 0,
        "population": [],
        "evaluated": [],
        "elite_candidates": [],
        "elite": [],
        "pareto_front": [],
        "score_cache": {},
        "best_prompt": state["base_prompt"],
        "best_score": -1.0,
        "best_metrics": {},
        "best_score_history": [],
        "pending_injections": [],
        "should_stop": False,
        "stop_reason": "",
        "logs": [f"Initialized. Task: {state['task_description']}"],
    }


def generate_variations(state: OptimizerState) -> dict:
    """Elitism (carry elites forward unchanged) + LLM mutation/crossover + any
    user-injected prompts, deduplicated, up to population_size candidates."""
    logs: list[str] = []
    generation = state["generation"] + 1
    pop_size = state["population_size"]
    elite = state["elite"]
    injections = state.get("pending_injections", [])

    candidates: list[dict] = []
    seen: set[str] = set()

    def add(prompt: str, source: str) -> None:
        prompt = (prompt or "").strip()
        if prompt and prompt not in seen:
            candidates.append({"prompt": prompt, "source": source})
            seen.add(prompt)

    for text in injections:
        add(text, "injected")
    if injections:
        logs.append(f"Injected {len(injections)} user-supplied prompt(s) into generation {generation}.")

    if not elite:
        add(state["base_prompt"], "base")
    else:
        for e in elite:
            add(e["prompt"], "elite")

    remaining = max(0, pop_size - len(candidates))
    if remaining:
        llm = _llm(state)
        mutate_n = remaining
        cross_n = 0
        if len(elite) >= 2 and remaining >= 2:
            cross_n = remaining // 2
            mutate_n = remaining - cross_n

        try:
            if mutate_n:
                seed = elite[0]["prompt"] if elite else state["base_prompt"]
                raw = llm.invoke(
                    MUTATION_PROMPT_TEMPLATE.format(
                        task_description=state["task_description"],
                        seed_prompt=seed,
                        count=mutate_n,
                        mutation_strength=state["mutation_strength"],
                    )
                ).content
                for text in json.loads(strip_json_fence(raw)):
                    add(text, "mutation")
        except Exception as exc:
            logs.append(f"Mutation generation failed ({exc}).")

        try:
            if cross_n:
                raw = llm.invoke(
                    CROSSOVER_PROMPT_TEMPLATE.format(
                        task_description=state["task_description"],
                        parent_a=elite[0]["prompt"],
                        parent_b=elite[1]["prompt"],
                        count=cross_n,
                    )
                ).content
                for text in json.loads(strip_json_fence(raw)):
                    add(text, "crossover")
        except Exception as exc:
            logs.append(f"Crossover generation failed ({exc}).")

    sources = ", ".join(c["source"] for c in candidates)
    logs.append(f"Generation {generation}: {len(candidates)} candidate prompt(s) ({sources}).")
    return {"generation": generation, "population": candidates, "pending_injections": [], "logs": logs}


def filter_by_diversity(state: OptimizerState) -> dict:
    """Reject candidates whose embedding is too similar (cosine sim > threshold)
    to an elite prompt or another candidate already kept this generation."""
    logs: list[str] = []
    population = state["population"]
    if not population:
        return {"logs": logs}

    threshold = state["diversity_threshold"]
    elite_vectors = [e["embedding"] for e in state["elite"] if e.get("embedding")]

    embeddings_client = evaluator.build_embeddings()
    vectors = evaluator.embed_texts(embeddings_client, [c["prompt"] for c in population], logs)
    if vectors is None:
        return {"logs": logs}  # embeddings unavailable this run: skip the filter, keep everything

    kept: list[dict] = []
    kept_vectors: list[list[float]] = []
    for candidate, vec in zip(population, vectors):
        candidate = {**candidate, "embedding": vec}
        sim = max_similarity(vec, elite_vectors + kept_vectors)
        if elite_vectors + kept_vectors and sim > threshold:
            logs.append(f"  rejected near-duplicate (sim={sim:.2f}): {candidate['prompt'][:60]}...")
            continue
        kept.append(candidate)
        kept_vectors.append(vec)

    if not kept:
        # never let a generation go empty: keep one candidate anyway
        kept = [{**population[0], "embedding": vectors[0]}]
        logs.append("  every candidate was a near-duplicate; kept one anyway.")

    logs.append(f"Diversity filter: kept {len(kept)}/{len(population)} (threshold={threshold}).")
    return {"population": kept, "logs": logs}


def evaluate_batch(state: OptimizerState) -> dict:
    """Score every surviving candidate on the full benchmark. Prompts already
    scored earlier in the run (e.g. carried-forward elites) are read from
    score_cache instead of re-spending judge calls on them."""
    logs: list[str] = []
    llm = _llm(state)
    benchmark = state["benchmark"]
    cache = dict(state.get("score_cache", {}))
    evaluated: list[dict] = []
    history_rows: list[dict] = []

    for candidate in state["population"]:
        cached = cache.get(candidate["prompt"])
        if cached:
            metrics, per_case = cached["metrics"], cached["per_case"]
            logs.append(f"  cache hit [{candidate['source']}]: {candidate['prompt'][:60]}...")
        else:
            metrics, per_case = evaluator.evaluate_prompt(llm, candidate["prompt"], benchmark, logs)
            cache[candidate["prompt"]] = {"metrics": metrics, "per_case": per_case}

        w_score = weighted_score(metrics, state["metric_weights"])
        evaluated.append({**candidate, "metrics": metrics, "weighted_score": w_score, "per_case": per_case})
        history_rows.append(
            {
                "generation": state["generation"],
                "source": candidate["source"],
                "prompt": candidate["prompt"],
                "weighted_score": round(w_score, 3),
                **{k: round(v, 2) for k, v in metrics.items()},
            }
        )
        logs.append(f"  scored [{candidate['source']}] weighted={w_score:.2f}: {candidate['prompt'][:60]}...")

    logs.append(f"Evaluated {len(evaluated)} candidate(s) on {len(benchmark)} benchmark case(s).")
    return {"evaluated": evaluated, "history": history_rows, "logs": logs, "score_cache": cache}


def multi_objective_selection(state: OptimizerState) -> dict:
    """Merge this generation's scores into the running elite pool, compute the
    Pareto front, and pick the next elite set per the chosen strategy."""
    logs: list[str] = []
    strategy = state["selection_strategy"]
    cap = max(state["population_size"], 3)

    pool = {c["prompt"]: c for c in state["elite"]}
    for c in state["evaluated"]:
        existing = pool.get(c["prompt"])
        if existing is None or c["weighted_score"] > existing["weighted_score"]:
            pool[c["prompt"]] = c
    pool_list = list(pool.values())

    front = pareto_front(pool_list, evaluator.ALL_METRICS)
    by_weighted = sorted(pool_list, key=lambda c: c["weighted_score"], reverse=True)

    if strategy == "weighted":
        new_elite = by_weighted[:cap]
    elif strategy == "pareto":
        new_elite = sorted(front, key=lambda c: c["weighted_score"], reverse=True)[:cap]
    else:  # hybrid (default): union of the Pareto front and the top-weighted, capped
        merged = {c["prompt"]: c for c in front}
        for c in by_weighted:
            if len(merged) >= cap:
                break
            merged[c["prompt"]] = c
        new_elite = sorted(merged.values(), key=lambda c: c["weighted_score"], reverse=True)[:cap]

    logs.append(f"Selection ({strategy}): pool={len(pool_list)}, pareto_front={len(front)}, new_elite={len(new_elite)}.")
    return {"pareto_front": front, "elite_candidates": new_elite, "logs": logs}


def update_elite(state: OptimizerState) -> dict:
    new_elite = state["elite_candidates"]
    best = max(new_elite, key=lambda c: c["weighted_score"]) if new_elite else None
    logs: list[str] = []

    result: dict = {"elite": new_elite, "population": [], "evaluated": []}
    if best and best["weighted_score"] > state["best_score"]:
        result["best_prompt"] = best["prompt"]
        result["best_score"] = best["weighted_score"]
        result["best_metrics"] = best["metrics"]
        logs.append(f"New best score: {best['weighted_score']:.2f}.")
    else:
        logs.append(f"No improvement this generation (best remains {state['best_score']:.2f}).")

    result["best_score_history"] = state["best_score_history"] + [result.get("best_score", state["best_score"])]
    result["logs"] = logs
    return result


def check_stopping_condition(state: OptimizerState) -> dict:
    logs: list[str] = []
    should_stop, reason = False, ""

    if state["generation"] >= state["max_generations"]:
        should_stop, reason = True, "reached max generations"
    else:
        recent = state["best_score_history"][-PLATEAU_WINDOW:]
        if len(recent) >= PLATEAU_WINDOW and (max(recent) - min(recent)) < PLATEAU_EPSILON:
            should_stop, reason = True, f"plateaued (best score flat for {PLATEAU_WINDOW} generations)"

    logs.append(f"Stopping check: {'STOP - ' + reason if should_stop else 'continue'}.")
    return {"should_stop": should_stop, "stop_reason": reason, "logs": logs}


def _route_after_stopping_check(state: OptimizerState) -> str:
    return "stop" if state["should_stop"] else "continue"


def build_graph():
    builder = StateGraph(OptimizerState)
    builder.add_node("initialize_population", initialize_population)
    builder.add_node("generate_variations", generate_variations)
    builder.add_node("filter_by_diversity", filter_by_diversity)
    builder.add_node("evaluate_batch", evaluate_batch)
    builder.add_node("multi_objective_selection", multi_objective_selection)
    builder.add_node("update_elite", update_elite)
    builder.add_node("check_stopping_condition", check_stopping_condition)

    builder.add_edge(START, "initialize_population")
    builder.add_edge("initialize_population", "generate_variations")
    builder.add_edge("generate_variations", "filter_by_diversity")
    builder.add_edge("filter_by_diversity", "evaluate_batch")
    builder.add_edge("evaluate_batch", "multi_objective_selection")
    builder.add_edge("multi_objective_selection", "update_elite")
    builder.add_edge("update_elite", "check_stopping_condition")
    builder.add_conditional_edges(
        "check_stopping_condition",
        _route_after_stopping_check,
        {"continue": "generate_variations", "stop": END},
    )

    # interrupt_before pauses the graph right before each new generation starts,
    # which is exactly where app.py wants to show progress / accept Stop or inject.
    return builder.compile(checkpointer=InMemorySaver(), interrupt_before=["generate_variations"])


def new_thread_config() -> dict:
    return {"configurable": {"thread_id": str(uuid.uuid4())}}
