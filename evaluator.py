"""Candidate execution and independent judging with explicit failure records."""

import statistics
from concurrent.futures import ThreadPoolExecutor

from contracts import METRICS, EvaluationResult, check_output, parse_json, validate_judgment
from prompts import judge_messages
from utils import weighted_score

ALL_METRICS = METRICS
JUDGED_METRICS = METRICS


def evaluate_case(runtime, contract, guidance, prompt, case, phase, repeat):
    result = {
        "id": case["id"],
        "input": case["input"],
        "guideline": case["guideline"],
        "repeat": repeat,
        "output": "",
        "scores": None,
        "rationale": "",
        "checks": [],
        "usage_ids": [],
        "error": None,
    }
    response = runtime.call("candidate", [("system", prompt), ("human", case["input"])], phase)
    result["usage_ids"].append(response.get("usage_id"))
    if response["status"] != "complete":
        return {
            **result,
            "status": "budget_skipped" if response["status"] == "budget_skipped" else "generation_failed",
            "error": response["error"],
        }
    result["output"] = response["text"]
    result["checks"] = check_output(response["text"], case["checks"])
    judgment = runtime.call(
        "judge", judge_messages(contract, guidance, prompt, case, response["text"]), phase
    )
    result["usage_ids"].append(judgment.get("usage_id"))
    if judgment["status"] != "complete":
        return {
            **result,
            "status": "budget_skipped" if judgment["status"] == "budget_skipped" else "judge_failed",
            "error": judgment["error"],
        }
    try:
        scores = validate_judgment(parse_json(judgment["text"]))
    except (ValueError, TypeError):
        return {**result, "status": "judge_failed", "error": {"type": "InvalidJudgment", "status_code": None}}
    result["scores"] = {metric: scores[metric] for metric in METRICS}
    result["rationale"] = scores["rationale"]
    return {
        **result,
        "status": "complete" if all(check["passed"] for check in result["checks"]) else "check_failed",
    }


def aggregate(prompt, rows) -> EvaluationResult:
    complete = bool(rows) and all(row["scores"] is not None for row in rows)
    metrics = {m: statistics.fmean(row["scores"][m] for row in rows) for m in METRICS} if complete else None
    per_case_means = {}
    for row in rows:
        if row["scores"]:
            per_case_means.setdefault(row["id"], []).append(statistics.fmean(row["scores"].values()))
    repeatability = None
    if complete and per_case_means and all(len(scores) > 1 for scores in per_case_means.values()):
        repeatability = statistics.fmean(statistics.pstdev(scores) for scores in per_case_means.values())
    return {
        "prompt": prompt,
        "status": "complete" if complete else "incomplete",
        "metrics": metrics,
        "per_case": rows,
        "eligible": complete and all(row["status"] == "complete" for row in rows),
        "cross_case_spread": statistics.pstdev([statistics.fmean(s) for s in per_case_means.values()])
        if complete
        else None,
        "repeatability": repeatability,
    }


def evaluate_prompts(runtime, contract, guidance, prompts, cases, phase="optimization", repeats=1):
    tasks = [(prompt, case, repeat) for prompt in prompts for repeat in range(repeats) for case in cases]

    def run(task):
        prompt, case, repeat = task
        return evaluate_case(runtime, contract, guidance, prompt, case, phase, repeat)

    with ThreadPoolExecutor(max_workers=runtime.concurrency) as pool:
        # map preserves input order even though requests complete out of order.
        rows = list(pool.map(run, tasks))
    size = len(cases) * repeats
    return [aggregate(prompt, rows[i * size : (i + 1) * size]) for i, prompt in enumerate(prompts)]


def failure_feedback(record):
    if not record:
        return []
    rows = sorted(
        record["per_case"],
        key=lambda row: (
            row["status"] == "complete",
            statistics.fmean(row["scores"].values()) if row["scores"] else -1,
        ),
    )[:3]
    return [
        {
            "case_id": row["id"],
            "input": row["input"][:400],
            "status": row["status"],
            "rationale": row["rationale"][:500],
            "failed_checks": [c for c in row["checks"] if not c["passed"]],
        }
        for row in rows
    ]


def comparison_report(baseline, candidate, weights):
    complete = baseline["status"] == candidate["status"] == "complete"
    same = baseline["prompt"] == candidate["prompt"]
    improved = (
        complete
        and not same
        and candidate["eligible"]
        and weighted_score(candidate["metrics"], weights) > weighted_score(baseline["metrics"], weights)
        and candidate["metrics"]["accuracy"] >= baseline["metrics"]["accuracy"]
    )
    regressions = []
    if complete:
        ids = dict.fromkeys(row["id"] for row in baseline["per_case"])
        for case_id in ids:
            a = aggregate(baseline["prompt"], [r for r in baseline["per_case"] if r["id"] == case_id])
            b = aggregate(candidate["prompt"], [r for r in candidate["per_case"] if r["id"] == case_id])
            assert a["metrics"] is not None and b["metrics"] is not None
            delta = {m: b["metrics"][m] - a["metrics"][m] for m in METRICS}
            if any(value < 0 for value in delta.values()) or not b["eligible"]:
                regressions.append({"case_id": case_id, "delta": delta, "checks_passed": b["eligible"]})
    return {
        "status": "complete" if complete else "incomplete",
        "improved": improved,
        "recommendation": candidate["prompt"] if improved else baseline["prompt"],
        "baseline": baseline,
        "candidate": candidate,
        "regressions": regressions,
        "note": "Observed differences on this benchmark; no statistical significance claim.",
    }
