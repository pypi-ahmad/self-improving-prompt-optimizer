"""Small pure-stdlib helpers shared by evaluator.py, benchmark.py and graph.py."""

import math


def strip_json_fence(text: str) -> str:
    """Strip a ```json ... ``` markdown fence if the LLM wrapped its JSON in one."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.removeprefix("json").strip()
    return text


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def max_similarity(embedding: list[float], others: list[list[float]]) -> float:
    if not others:
        return 0.0
    return max(cosine_similarity(embedding, o) for o in others)


def normalized_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        n = len(weights) or 1
        return {k: 1.0 / n for k in weights}
    return {k: v / total for k, v in weights.items()}


def weighted_score(metrics: dict[str, float], weights: dict[str, float]) -> float:
    norm = normalized_weights(weights)
    return sum(metrics.get(k, 0.0) * w for k, w in norm.items())


def is_dominated(candidate: dict, other: dict, metric_keys: list[str]) -> bool:
    """True if `other` dominates `candidate`: other is >= on every metric and
    strictly better on at least one."""
    at_least_equal = all(other[k] >= candidate[k] for k in metric_keys)
    strictly_better = any(other[k] > candidate[k] for k in metric_keys)
    return at_least_equal and strictly_better


def pareto_front(candidates: list[dict], metric_keys: list[str]) -> list[dict]:
    """Non-dominated subset of `candidates`, each item exposing `metrics` dict.
    ponytail: O(n^2) pairwise dominance check, fine for population sizes this
    app targets (tens, not thousands); switch to a sweep algorithm if that changes.
    """
    scored = [c for c in candidates if c.get("metrics")]
    front = []
    for c in scored:
        c_metrics = c["metrics"]
        dominated = any(
            is_dominated(c_metrics, other["metrics"], metric_keys)
            for other in scored
            if other is not c
        )
        if not dominated:
            front.append(c)
    return front
