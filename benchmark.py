"""Fixed benchmark + optional LLM-generated benchmark.

Each test case is `{"input": str, "guideline": str}`. To change the domain,
either edit DEFAULT_BENCHMARK below or use `generate_benchmark()` from the UI.
"""

import json
from pathlib import Path

from prompts import BENCHMARK_GENERATION_PROMPT_TEMPLATE
from utils import strip_json_fence

GENERATED_BENCHMARK_PATH = Path(__file__).parent / "data" / "generated_benchmark.json"

DEFAULT_BENCHMARK = [
    {
        "input": "hey can u send me the report by tmrw morning, need it for the meeting thx",
        "guideline": "Should read as a professional, clear, actionable request with a concrete deadline; casual abbreviations removed.",
    },
    {
        "input": "The server went down again and nobody knows why, this is the third time this month and honestly the on-call process is a mess and someone needs to fix it",
        "guideline": "Should stay factual and actionable (report the incident, note the recurrence, request a process fix) without sounding like a rant.",
    },
    {
        "input": "im not sure if this makes sense but maybe we could possibly think about changing the deploy pipeline at some point if people agree",
        "guideline": "Should convert the hedging into a clear, direct proposal while preserving that it is a proposal, not a decision.",
    },
    {
        "input": "Please find attached the document. Let me know if you have any questions or concerns or issues or anything at all really.",
        "guideline": "Should tighten the redundant closing phrase and stay concise while remaining polite and complete.",
    },
    {
        "input": "we need more budget for the project. its important",
        "guideline": "Should expand into a professional, actionable ask (what budget, for what, by when) without inventing facts not implied by the input.",
    },
    {
        "input": "Following up on my previous email from last week regarding the invoice that I sent which I believe you may not have seen yet, just wanted to check in",
        "guideline": "Should compress the wordy follow-up into a short, direct, professional nudge that preserves the original intent.",
    },
    {
        "input": "stop doing that, it's wrong and everyone knows it",
        "guideline": "Should professionalize tone (remove bluntness/accusation) while preserving the core corrective intent, not softening it into meaninglessness.",
    },
    {
        "input": "Quick q - are we still on for the 3pm? also do you have the slides? and one more thing, can someone book the room",
        "guideline": "Should organize the three bundled asks into clear, separate, actionable items.",
    },
]


def load_benchmark(use_generated: bool) -> list[dict]:
    if use_generated and GENERATED_BENCHMARK_PATH.exists():
        try:
            return json.loads(GENERATED_BENCHMARK_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_BENCHMARK


def save_benchmark(cases: list[dict]) -> None:
    GENERATED_BENCHMARK_PATH.parent.mkdir(parents=True, exist_ok=True)
    GENERATED_BENCHMARK_PATH.write_text(json.dumps(cases, indent=2), encoding="utf-8")


def generate_benchmark(llm, task_description: str, count: int = 7) -> list[dict]:
    """Ask the LLM to design `count` diverse test cases for task_description."""
    prompt = BENCHMARK_GENERATION_PROMPT_TEMPLATE.format(
        task_description=task_description, count=count
    )
    raw = llm.invoke(prompt).content
    cases = json.loads(strip_json_fence(raw))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Benchmark generation returned no test cases.")
    cleaned = [
        {"input": str(c["input"]), "guideline": str(c["guideline"])}
        for c in cases
        if "input" in c and "guideline" in c
    ]
    if not cleaned:
        raise ValueError("Benchmark generation returned malformed test cases.")
    return cleaned
