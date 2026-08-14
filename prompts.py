"""Prompt templates: the default optimization target plus every meta-prompt
used to mutate/crossover candidates, judge outputs, and auto-generate a
benchmark. Edit these strings to retarget the optimizer at a new task.
"""

DEFAULT_TASK_DESCRIPTION = (
    "Improve the following user message to be more professional, clear, and actionable."
)

DEFAULT_BASE_PROMPT = (
    "You are an expert editor. Rewrite the user's message so it is more "
    "professional, clear, and actionable, while preserving its original intent "
    "and all factual content. Return only the rewritten message."
)

METRIC_NAMES = ["accuracy", "clarity", "conciseness", "helpfulness", "consistency"]

# ---------------------------------------------------------------------------
# Variation generation (mutation + crossover)
# ---------------------------------------------------------------------------

MUTATION_PROMPT_TEMPLATE = """You are optimizing a system prompt for this task:
"{task_description}"

Current prompt (seed):
---
{seed_prompt}
---

Write {count} DISTINCT rewritten versions of this prompt that try to score higher on:
accuracy/faithfulness, clarity, conciseness, helpfulness, and consistency across varied inputs.

Mutation strength: {mutation_strength}. At "low" strength make small wording tweaks; at
"high" strength try structurally different instructions (e.g. add constraints, add examples,
change ordering, add explicit output format).

Respond with ONLY a JSON array of {count} strings, each a full standalone prompt. No prose,
no markdown fences, no numbering.
"""

CROSSOVER_PROMPT_TEMPLATE = """You are optimizing a system prompt for this task:
"{task_description}"

Combine the strongest elements of these two high-performing prompts into {count} new,
DISTINCT hybrid prompts. Keep whatever made each parent effective; drop what likely hurt it.

Parent A:
---
{parent_a}
---

Parent B:
---
{parent_b}
---

Respond with ONLY a JSON array of {count} strings, each a full standalone prompt. No prose,
no markdown fences, no numbering.
"""

# ---------------------------------------------------------------------------
# LLM-as-judge
# ---------------------------------------------------------------------------

JUDGE_PROMPT_TEMPLATE = """You are a strict evaluator scoring how well an AI response handled a task.

Task instruction given to the AI (the candidate prompt being tested):
---
{candidate_prompt}
---

Input the AI was given:
---
{input_text}
---

Evaluation guideline for this test case:
---
{guideline}
---

The AI's response:
---
{output_text}
---

Score the response 1 (worst) to 10 (best) on each dimension:
- accuracy: correctly follows the instruction and preserves the input's factual content/intent
- clarity: easy to understand, unambiguous
- conciseness: no unnecessary verbosity or padding
- helpfulness: overall usefulness of the response for the stated goal

Respond with ONLY a JSON object, no prose, no markdown fences:
{{"accuracy": <1-10>, "clarity": <1-10>, "conciseness": <1-10>, "helpfulness": <1-10>, "reasoning": "<one short sentence>"}}
"""

# ---------------------------------------------------------------------------
# Automatic benchmark generation
# ---------------------------------------------------------------------------

BENCHMARK_GENERATION_PROMPT_TEMPLATE = """Design an evaluation benchmark for this task:
"{task_description}"

Produce {count} diverse test cases that together stress different edge cases (short input,
long input, ambiguous input, informal input, input with typos, input with mixed intents, etc).

Respond with ONLY a JSON array of {count} objects, no prose, no markdown fences:
[{{"input": "<realistic input text for the task>", "guideline": "<what a good response must do for this specific case>"}}, ...]
"""
