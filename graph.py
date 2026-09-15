"""Checkpointed search, finalist re-evaluation, and isolated holdout validation."""

import copy
import math
import operator
import uuid
from typing import Annotated, Any, TypedDict, cast

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from benchmark import validate_benchmark
from contracts import METRICS, fingerprint, parse_json, sanitize, validate_variations
from evaluator import comparison_report, evaluate_prompts, failure_feedback
from prompts import variation_messages
from utils import max_similarity, pareto_front, weighted_score

PLATEAU_WINDOW = 3
PLATEAU_EPSILON = 0.05


class OptimizerState(TypedDict, total=False):
    contract: dict
    benchmark: dict
    guidance: dict
    models: dict
    settings: dict
    generation: int
    phase: str
    population: list[dict]
    elite: list[dict]
    pareto_front: list[dict]
    score_cache: dict[str, dict]
    embedding_cache: dict[str, list[float]]
    baseline: dict
    best_prompt: str
    best_score: float
    best_metrics: dict
    best_score_history: list[float]
    pending_injections: list[str]
    stop_reason: str
    should_stop: bool
    finalists: list[dict]
    selected_prompt: str
    comparison: dict
    usage: dict
    cache_hits: int
    history: Annotated[list[dict], operator.add]
    logs: Annotated[list[str], operator.add]


def make_initial_state(contract, benchmark, guidance, models, **settings):
    defaults = {
        "population_size": 6,
        "max_generations": 5,
        "mutation_strength": "medium",
        "metric_weights": dict.fromkeys(METRICS, 1.0),
        "selection_strategy": "hybrid",
        "diversity_threshold": 0.92,
        "embedding_model": "text-embedding-3-small",
    }
    if set(settings) - set(defaults):
        raise ValueError("Unknown optimizer setting.")
    defaults.update(settings)
    if any(type(defaults[key]) is not int for key in ("population_size", "max_generations")):
        raise ValueError("Population and generation counts must be integers.")
    if not 2 <= defaults["population_size"] <= 20 or not 1 <= defaults["max_generations"] <= 30:
        raise ValueError("Population or generation count is outside the supported range.")
    if defaults["selection_strategy"] not in {"weighted", "pareto", "hybrid"} or defaults[
        "mutation_strength"
    ] not in {"low", "medium", "high"}:
        raise ValueError("Invalid search strategy or mutation strength.")
    weights = defaults["metric_weights"]
    if (
        set(weights) != set(METRICS)
        or any(not isinstance(v, (float, int)) or not 0 <= v <= 2 for v in weights.values())
        or sum(weights.values()) == 0
    ):
        raise ValueError("Set nonnegative metric weights with at least one positive weight.")
    if not 0.5 <= defaults["diversity_threshold"] <= 0.99:
        raise ValueError("Invalid diversity threshold.")
    if any(literal not in contract["base_prompt"] for literal in contract["protected_literals"]):
        raise ValueError("Each protected prompt literal must occur in the base prompt.")
    return copy.deepcopy(
        {
            "contract": contract,
            "benchmark": validate_benchmark(benchmark, contract),
            "guidance": guidance,
            "models": models,
            "settings": defaults,
        }
    )


def cache_key(state, prompt):
    return fingerprint(
        {
            "prompt": prompt,
            "contract": state["contract"],
            "benchmark": state["benchmark"]["hash"],
            "guidance": state["guidance"]["hashes"],
            "models": state["models"],
            "evaluator_version": 1,
        }
    )


def score_record(record, weights, source):
    return {
        **record,
        "source": source,
        "weighted_score": weighted_score(record["metrics"], weights) if record["metrics"] else None,
    }


def finalization_estimate(state, runtime):
    count = min(2, len([e for e in state["elite"] if e["prompt"] != state["contract"]["base_prompt"]])) + 1
    pairs = count * len(state["benchmark"]["optimization"]) * 2 + 2 * len(state["benchmark"]["holdout"]) * 2
    events = runtime.snapshot()["events"]
    costs = []
    for role in ("candidate", "judge"):
        charges = [e["charged_usd"] for e in events if e["role"] == role]
        costs.append(
            sum(charges) / len(charges) if charges else runtime.estimate(role, [("human", "validation")])
        )
    return pairs * sum(costs), pairs * 2


def build_graph(runtime):
    def initialize(state):
        base = state["contract"]["base_prompt"]
        result = evaluate_prompts(
            runtime, state["contract"], state["guidance"], [base], state["benchmark"]["optimization"]
        )[0]
        baseline = score_record(result, state["settings"]["metric_weights"], "base")
        cache = {cache_key(state, base): baseline} if result["status"] == "complete" else {}
        return {
            "generation": 0,
            "phase": "search",
            "population": [],
            "elite": [baseline] if baseline["eligible"] else [],
            "pareto_front": [],
            "score_cache": cache,
            "embedding_cache": {},
            "baseline": baseline,
            "best_prompt": base,
            "best_score": baseline["weighted_score"] if baseline["eligible"] else -1.0,
            "best_metrics": baseline["metrics"] or {},
            "best_score_history": [],
            "pending_injections": [],
            "should_stop": False,
            "stop_reason": "",
            "cache_hits": 0,
            "history": [{"generation": 0, **baseline}],
            "usage": runtime.snapshot(),
            "logs": ["Evaluated baseline against optimization cases; holdout remains isolated."],
        }

    def generate(state):
        logs, candidates, seen = [], [], set()
        cap = state["settings"]["population_size"]
        elites = state["elite"][: max(1, cap // 2)]

        def add(text, source):
            text = sanitize(text.strip())
            if text and text not in seen and len(candidates) < cap:
                candidates.append({"prompt": text, "source": source})
                seen.add(text)

        for elite in elites:
            add(elite["prompt"], "elite")
        if not elites:
            add(state["contract"]["base_prompt"], "base")
        pending = list(state.get("pending_injections", []))
        while pending and len(candidates) < cap:
            text = pending.pop(0)
            if all(lit in text for lit in state["contract"]["protected_literals"]):
                add(text, "injected")
            else:
                logs.append("Rejected injection missing a protected prompt literal.")
        remaining = cap - len(candidates)
        cross = remaining // 2 if len(elites) >= 2 else 0
        parents = [e["prompt"] for e in elites[:2]] or [state["contract"]["base_prompt"]]
        for source, count in (("mutation", remaining - cross), ("crossover", cross)):
            if not count:
                continue
            selected = parents[:1] if source == "mutation" else parents
            feedback = [failure_feedback(state["score_cache"].get(cache_key(state, p))) for p in selected]
            messages = variation_messages(
                state["contract"],
                state["guidance"],
                selected,
                count,
                state["settings"]["mutation_strength"],
                feedback,
            )
            response = runtime.call("generation", messages, source)
            if response["status"] != "complete":
                logs.append(f"{source}: {response['status']} ({response['error']['type']}).")
                continue
            try:
                for text in validate_variations(parse_json(response["text"]), count, state["contract"]):
                    add(text, source)
            except (ValueError, TypeError):
                logs.append(f"{source}: invalid candidate array.")
        return {
            "generation": state["generation"] + 1,
            "population": candidates,
            "pending_injections": pending,
            "logs": logs + [f"Prepared {len(candidates)} candidates; {len(pending)} injections queued."],
            "usage": runtime.snapshot(),
        }

    def diversity(state):
        model = state["settings"]["embedding_model"]
        cache = dict(state["embedding_cache"])
        candidates = state["population"]
        missing = [c["prompt"] for c in candidates if c["prompt"] not in cache]
        if missing:
            response = runtime.embed(missing, model)
            if response["status"] != "complete":
                return {
                    "logs": [
                        f"Semantic diversity unavailable ({response['status']}); exact deduplication applied."
                    ],
                    "usage": runtime.snapshot(),
                }
            vectors = response.get("vectors")
            all_vectors = list(cache.values()) + (vectors if isinstance(vectors, list) else [])
            valid = (
                isinstance(vectors, list)
                and len(vectors) == len(missing)
                and all_vectors
                and all(
                    isinstance(vec, list)
                    and vec
                    and all(
                        isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
                        for x in vec
                    )
                    for vec in all_vectors
                )
                and len({len(vec) for vec in all_vectors}) == 1
            )
            if not valid:
                return {
                    "logs": ["Invalid embeddings; exact deduplication applied."],
                    "usage": runtime.snapshot(),
                }
            cache.update(zip(missing, vectors))
        kept = [c for c in candidates if c["source"] in {"elite", "base"}]
        vectors = [cache[c["prompt"]] for c in kept]
        for candidate in candidates:
            if candidate in kept:
                continue
            vec = cache[candidate["prompt"]]
            if not vectors or max_similarity(vec, vectors) <= state["settings"]["diversity_threshold"]:
                kept.append(candidate)
                vectors.append(vec)
        return {"population": kept, "embedding_cache": cache, "usage": runtime.snapshot()}

    def evaluate(state):
        cache = dict(state["score_cache"])
        candidates = state["population"]
        missing = [c["prompt"] for c in candidates if cache_key(state, c["prompt"]) not in cache]
        fresh = (
            evaluate_prompts(
                runtime, state["contract"], state["guidance"], missing, state["benchmark"]["optimization"]
            )
            if missing
            else []
        )
        by_prompt = {result["prompt"]: result for result in fresh}
        rows = []
        for candidate in candidates:
            key = cache_key(state, candidate["prompt"])
            result = cache.get(key) or by_prompt[candidate["prompt"]]
            record = score_record(result, state["settings"]["metric_weights"], candidate["source"])
            rows.append(record)
            if record["status"] == "complete":
                cache[key] = record
        pool = {e["prompt"]: e for e in state["elite"]}
        for record in rows:
            if record["eligible"]:
                pool[record["prompt"]] = record
        weights = state["settings"]["metric_weights"]
        ordered = sorted(pool.values(), key=lambda e: (-weighted_score(e["metrics"], weights), e["prompt"]))
        front = pareto_front(ordered, METRICS)
        strategy = state["settings"]["selection_strategy"]
        if strategy == "pareto":
            selected = front
        elif strategy == "hybrid":
            selected = list({e["prompt"]: e for e in front + ordered}.values())
        else:
            selected = ordered
        elite = selected[: state["settings"]["population_size"]]
        best = ordered[0] if ordered else None
        best_score = best["weighted_score"] if best else state["best_score"]
        return {
            "score_cache": cache,
            "population": [],
            "elite": elite,
            "pareto_front": front,
            "best_prompt": best["prompt"] if best else state["best_prompt"],
            "best_score": best_score,
            "best_metrics": best["metrics"] if best else state["best_metrics"],
            "best_score_history": state["best_score_history"] + [best_score],
            "cache_hits": state["cache_hits"] + len(candidates) - len(missing),
            "history": [{"generation": state["generation"], **row} for row in rows],
            "usage": runtime.snapshot(),
        }

    def stopping(state):
        recent = state["best_score_history"][-PLATEAU_WINDOW:]
        estimate, calls = finalization_estimate(state, runtime)
        free_slots = state["settings"]["population_size"] - min(
            len(state["elite"]), state["settings"]["population_size"] // 2
        )
        next_calls = free_slots * len(state["benchmark"]["optimization"]) * 2 + 2
        next_cost = estimate / calls * next_calls if calls else 0
        reason = ""
        if state["generation"] >= state["settings"]["max_generations"]:
            reason = "reached max generations"
        elif not runtime.can_afford(estimate + next_cost, calls + next_calls):
            reason = "remaining allowance reserved for validation"
        elif len(recent) == PLATEAU_WINDOW and max(recent) - min(recent) < PLATEAU_EPSILON:
            reason = "plateaued"
        return {
            "should_stop": bool(reason),
            "stop_reason": reason,
            "phase": "finalists" if reason else "search",
            "logs": [reason or "Continuing search."],
        }

    def finalists(state):
        base = state["contract"]["base_prompt"]
        ranked = sorted(state["elite"], key=lambda e: -e["weighted_score"])
        prompts = [base] + [e["prompt"] for e in ranked if e["prompt"] != base][:2]
        results = evaluate_prompts(
            runtime,
            state["contract"],
            state["guidance"],
            prompts,
            state["benchmark"]["optimization"],
            "finalists",
            repeats=2,
        )
        eligible = [r for r in results if r["eligible"]]
        chosen = (
            max(eligible, key=lambda r: weighted_score(r["metrics"], state["settings"]["metric_weights"]))
            if eligible
            else results[0]
        )
        return {
            "finalists": results,
            "selected_prompt": chosen["prompt"],
            "phase": "holdout",
            "usage": runtime.snapshot(),
        }

    def holdout(state):
        base = state["contract"]["base_prompt"]
        prompts = list(dict.fromkeys([base, state["selected_prompt"]]))
        results = evaluate_prompts(
            runtime,
            state["contract"],
            state["guidance"],
            prompts,
            state["benchmark"]["holdout"],
            "holdout",
            repeats=2,
        )
        report = comparison_report(results[0], results[-1], state["settings"]["metric_weights"])
        if any(r["status"] != "complete" for r in state["finalists"]):
            report.update(status="incomplete", improved=False, recommendation=base)
        return {
            "comparison": report,
            "phase": "finished",
            "usage": runtime.snapshot(),
            "logs": [f"Validation {report['status']}. Holdout results were not used for selection."],
        }

    # LangGraph's structural TypedDict bound is not recognized by ty on Python 3.13.
    builder = StateGraph(cast(Any, OptimizerState))
    for name, function in (
        ("initialize", initialize),
        ("generate", generate),
        ("diversity", diversity),
        ("evaluate", evaluate),
        ("stopping", stopping),
        ("finalists", finalists),
        ("holdout", holdout),
    ):
        builder.add_node(name, function)
    builder.add_edge(START, "initialize")
    builder.add_edge("initialize", "generate")
    builder.add_edge("generate", "diversity")
    builder.add_edge("diversity", "evaluate")
    builder.add_edge("evaluate", "stopping")
    builder.add_conditional_edges(
        "stopping", lambda state: "finalists" if state["should_stop"] else "generate"
    )
    builder.add_edge("finalists", "holdout")
    builder.add_edge("holdout", END)
    return builder.compile(
        checkpointer=InMemorySaver(), interrupt_before=["generate", "finalists", "holdout"]
    )


def new_thread_config() -> dict:
    return {"configurable": {"thread_id": str(uuid.uuid4())}}
