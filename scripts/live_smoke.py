"""Run the authorized smoke test under one persistent 80-attempt / $6 ledger."""

import json
from pathlib import Path

from dotenv import load_dotenv

from benchmark import builtin_benchmark, validate_benchmark
from contracts import guidance_snapshot, make_contract
from graph import build_graph, make_initial_state, new_thread_config
from prompts import DEFAULT_BASE_PROMPT, DEFAULT_TASK_DESCRIPTION
from reporting import export_run
from runtime import Runtime

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"


def main():
    load_dotenv()
    runtime = Runtime(
        usd_cap=6.0, call_cap=80, concurrency=4, ledger_path=ARTIFACTS / "verification_budget.json"
    )
    contract = make_contract(DEFAULT_TASK_DESCRIPTION, DEFAULT_BASE_PROMPT)
    built = builtin_benchmark(contract)
    benchmark = validate_benchmark(
        {"optimization": built["optimization"][:2], "holdout": built["holdout"][:2]}, contract
    )
    graph = build_graph(runtime)
    thread = new_thread_config()
    state = graph.invoke(
        make_initial_state(
            contract, benchmark, guidance_snapshot(), runtime.models, population_size=4, max_generations=2
        ),
        thread,
    )
    while True:
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        (ARTIFACTS / "live_smoke.json").write_text(export_run(state, runtime), encoding="utf-8")
        usage = runtime.snapshot()
        print(
            json.dumps(
                {
                    "phase": state["phase"],
                    "generation": state["generation"],
                    "calls": usage["calls"],
                    "estimated_usd": usage["charged_usd"],
                    "failures": sum(e["status"] == "failed" for e in usage["events"]),
                }
            ),
            flush=True,
        )
        if state["baseline"]["status"] != "complete":
            print("Baseline evaluation incomplete; inspect sanitized artifacts before retrying.", flush=True)
            return 1
        if not graph.get_state(thread).next:
            return 0 if state["comparison"]["status"] == "complete" else 1
        state = graph.invoke(None, thread)


if __name__ == "__main__":
    raise SystemExit(main())
