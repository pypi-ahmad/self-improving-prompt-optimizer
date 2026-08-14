"""LLM execution, LLM-as-judge scoring, and embeddings.

All model calls go through here so graph.py stays free of prompt-formatting
and API-shape details.
"""

import json
import os
import statistics

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from openai import OpenAI

from prompts import JUDGE_PROMPT_TEMPLATE
from utils import strip_json_fence

JUDGED_METRICS = ["accuracy", "clarity", "conciseness", "helpfulness"]
ALL_METRICS = JUDGED_METRICS + ["consistency"]

FALLBACK_MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"]
PREFERRED_DEFAULTS = ["gpt-4.1-mini", "gpt-4o-mini", "gpt-5-mini", "gpt-4o", "gpt-4.1"]


def _base_url() -> str | None:
    return os.environ.get("OPENAI_BASE_URL") or None


def build_llm(model_name: str, temperature: float) -> ChatOpenAI:
    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=_base_url(),
    )


def build_embeddings(model_name: str = "text-embedding-3-small") -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=model_name,
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=_base_url(),
    )


def list_available_models() -> list[str]:
    """Best-effort chat-model list from the configured base URL, with a
    sensible small/cheap model sorted first. Excludes fine-tuned deployments
    (their ids contain ':') since a benchmark run isn't the place to pick one.
    Falls back to a short hardcoded list if the endpoint doesn't expose /models."""
    try:
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=_base_url())
        ids = sorted(m.id for m in client.models.list().data if ":" not in m.id)
        if not ids:
            return FALLBACK_MODELS
        preferred = [m for m in PREFERRED_DEFAULTS if m in ids]
        rest = [m for m in ids if m not in preferred]
        return preferred + rest
    except Exception:
        return FALLBACK_MODELS


def run_candidate_prompt(llm: ChatOpenAI, candidate_prompt: str, input_text: str) -> str:
    messages = [("system", candidate_prompt), ("human", input_text)]
    return llm.invoke(messages).content


def judge_output(
    llm: ChatOpenAI, candidate_prompt: str, case: dict, output_text: str, log: list[str]
) -> dict:
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        candidate_prompt=candidate_prompt,
        input_text=case["input"],
        guideline=case["guideline"],
        output_text=output_text,
    )
    try:
        raw = llm.invoke(prompt).content
        data = json.loads(strip_json_fence(raw))
        return {m: float(data[m]) for m in JUDGED_METRICS}
    except Exception as exc:
        log.append(f"  judge parse failed ({exc}); using neutral fallback scores")
        return {m: 5.0 for m in JUDGED_METRICS}


def consistency_score(per_case_overall: list[float]) -> float:
    """10 = identical quality across every test case, lower = more variance."""
    if len(per_case_overall) < 2:
        return 10.0
    spread = statistics.pstdev(per_case_overall)
    # ponytail: linear penalty on stdev, tune the 3.0 scale if it feels too harsh/lenient
    return max(0.0, 10.0 - spread * 3.0)


def evaluate_prompt(
    llm: ChatOpenAI, candidate_prompt: str, benchmark: list[dict], log: list[str]
) -> tuple[dict, list[dict]]:
    """Run `candidate_prompt` against every benchmark case and judge each output.
    Returns (averaged_metrics incl. consistency, per_case_detail)."""
    per_case = []
    for case in benchmark:
        try:
            output = run_candidate_prompt(llm, candidate_prompt, case["input"])
        except Exception as exc:
            log.append(f"  generation failed for case '{case['input'][:40]}...': {exc}")
            output = ""
        scores = judge_output(llm, candidate_prompt, case, output, log)
        per_case.append({"input": case["input"], "output": output, **scores})

    if not per_case:
        return {m: 0.0 for m in ALL_METRICS}, per_case

    averaged = {m: statistics.fmean(c[m] for c in per_case) for m in JUDGED_METRICS}
    per_case_overall = [statistics.fmean(c[m] for m in JUDGED_METRICS) for c in per_case]
    averaged["consistency"] = consistency_score(per_case_overall)
    return averaged, per_case


def embed_texts(embeddings: OpenAIEmbeddings, texts: list[str], log: list[str]) -> list[list[float]] | None:
    """Returns None (rather than raising) if the endpoint can't embed, so
    diversity filtering can degrade gracefully instead of crashing the run."""
    if not texts:
        return []
    try:
        return embeddings.embed_documents(texts)
    except Exception as exc:
        log.append(f"  embeddings unavailable ({exc}); skipping diversity filter this generation")
        return None
