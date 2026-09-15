import json

import pytest

from evaluator import evaluate_prompts
from graph import build_graph, cache_key, make_initial_state, new_thread_config
from reporting import export_run, history_csv
from runtime import PRICES, Runtime


def run_graph(runtime, contract, bundle, guidance, **settings):
    graph = build_graph(runtime)
    thread = new_thread_config()
    state = graph.invoke(make_initial_state(contract, bundle, guidance, runtime.models, **settings), thread)
    while graph.get_state(thread).next:
        state = graph.invoke(None, thread)
    return graph, thread, state


@pytest.mark.parametrize("strategy", ["weighted", "pareto", "hybrid"])
def test_search_finalists_and_holdout(provider, contract, bundle, guidance, strategy):
    runtime = Runtime(adapter=provider)
    graph, thread, state = run_graph(
        runtime, contract, bundle, guidance, population_size=4, max_generations=2, selection_strategy=strategy
    )
    assert state["generation"] == 2
    assert state["comparison"]["status"] == "complete"
    assert state["comparison"]["improved"]
    assert all(r["repeatability"] is not None for r in state["finalists"])
    assert all(len(r["per_case"]) == 4 for r in state["finalists"])
    assert any(e["phase"] == "crossover" for e in runtime.snapshot()["events"])
    for role, _settings, payload in provider.calls:
        if role == "generation":
            assert all(case["input"] not in payload[-1][1] for case in bundle["holdout"])
    assert len([r for r in state["history"] if r["generation"] == 2]) <= 4
    assert any(r["source"] in {"mutation", "crossover"} and r["generation"] == 2 for r in state["history"])
    assert state["cache_hits"] > 0
    assert not graph.get_state(thread).next
    report = json.loads(export_run(state, runtime))
    assert report["schema_version"] == 1
    assert report["run"]["benchmark"]["hash"] == bundle["hash"]
    assert "weighted_score" in history_csv(state)


def test_failures_cannot_win(contract, bundle, guidance):
    runtime = Runtime(adapter=lambda *_: {"text": "{}"})
    _, _, state = run_graph(runtime, contract, bundle, guidance, max_generations=1)
    assert not state["elite"]
    assert state["comparison"]["status"] == "incomplete"
    assert state["comparison"]["recommendation"] == contract["base_prompt"]
    assert all(r["weighted_score"] is None for r in state["history"])


def test_budget_exhaustion_is_incomplete(provider, contract, bundle, guidance):
    runtime = Runtime(adapter=provider, call_cap=2)
    _, _, state = run_graph(runtime, contract, bundle, guidance, max_generations=1)
    assert runtime.snapshot()["calls"] == 2
    assert state["comparison"]["status"] == "incomplete"
    assert not state["comparison"]["improved"]


def test_checks_and_cache_fingerprint(provider, contract, bundle, guidance):
    runtime = Runtime(adapter=provider)
    bundle["optimization"][0]["checks"] = {"required_literals": ["MISSING"]}
    result = evaluate_prompts(runtime, contract, guidance, [contract["base_prompt"]], bundle["optimization"])[
        0
    ]
    assert result["status"] == "complete" and not result["eligible"]
    state = make_initial_state(contract, bundle, guidance, runtime.models)
    key = cache_key(state, contract["base_prompt"])
    state["models"]["judge"]["reasoning_effort"] = "high"
    assert cache_key(state, contract["base_prompt"]) != key


def test_injection_queue_and_checkpoint(provider, contract, bundle, guidance):
    runtime = Runtime(adapter=provider)
    graph = build_graph(runtime)
    thread = new_thread_config()
    graph.invoke(
        make_initial_state(contract, bundle, guidance, runtime.models, population_size=2, max_generations=2),
        thread,
    )
    before = runtime.snapshot()["calls"]
    graph.get_state(thread)
    assert runtime.snapshot()["calls"] == before
    graph.update_state(thread, {"pending_injections": ["Injected A", "Injected B", "Injected C"]})
    state = graph.invoke(None, thread)
    assert len(state["pending_injections"]) == 2
    assert len([r for r in state["history"] if r["generation"] == 1]) == 2


def test_search_leaves_calls_for_validation(provider, contract, bundle, guidance):
    runtime = Runtime(adapter=provider, call_cap=70)
    _, _, state = run_graph(runtime, contract, bundle, guidance, population_size=4, max_generations=10)
    assert state["stop_reason"] == "remaining allowance reserved for validation"
    assert state["comparison"]["status"] == "complete"
    assert runtime.snapshot()["calls"] <= 70


def test_priced_embeddings_preserve_elites(provider, contract, bundle, guidance):
    runtime = Runtime(
        adapter=provider,
        prices={**PRICES, "text-embedding-3-small": {"input": 0.02, "cached_input": 0.02, "output": 0}},
    )
    _, _, state = run_graph(runtime, contract, bundle, guidance, population_size=4, max_generations=2)
    assert state["embedding_cache"]
    assert any(r["source"] == "elite" and r["generation"] == 2 for r in state["history"])
    assert any(e["role"] == "embedding" for e in runtime.snapshot()["events"])


def test_bad_embeddings_fall_back(provider, contract, bundle, guidance):
    def adapter(role, settings, payload):
        if role == "embedding":
            return {"vectors": [[float("nan")]] * len(payload)}
        return provider(role, settings, payload)

    runtime = Runtime(
        adapter=adapter,
        prices={**PRICES, "text-embedding-3-small": {"input": 0.02, "cached_input": 0.02, "output": 0}},
    )
    _, _, state = run_graph(runtime, contract, bundle, guidance, population_size=4, max_generations=1)
    assert not state["embedding_cache"]
    assert len([r for r in state["history"] if r["generation"] == 1]) == 4
