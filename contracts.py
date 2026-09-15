"""Serializable contracts and strict, offline validation shared by the app."""

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, TypedDict

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

METRICS = ["accuracy", "clarity", "conciseness", "helpfulness"]
GUIDANCE_DIR = Path(__file__).parent / "guidance"


class TaskContract(TypedDict):
    task_description: str
    base_prompt: str
    constraints: str
    protected_literals: list[str]


class ModelSettings(TypedDict):
    model: str
    reasoning_effort: str | None
    temperature: float | None
    max_completion_tokens: int


class EvaluationResult(TypedDict):
    status: str
    prompt: str
    metrics: dict[str, float] | None
    per_case: list[dict]
    eligible: bool
    cross_case_spread: float | None
    repeatability: float | None


def fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()


def sanitize(value: Any) -> Any:
    """Redact high-confidence credentials, not ordinary identifiers or paths."""
    if isinstance(value, dict):
        return {
            key: "${REDACTED_SECRET}"
            if isinstance(item, str)
            and re.fullmatch(r"(?i)(?:api[_ -]?key|access[_ -]?token|password|secret)", str(key))
            and not item.startswith(("${", "[", "<"))
            else sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if not isinstance(value, str):
        return value
    value = re.sub(
        r"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b",
        "${API_TOKEN}",
        value,
    )
    return re.sub(
        r"(?i)(\b(?:api[_ -]?key|access[_ -]?token|password|secret)[\"']?\s*[:=]\s*)"
        r"(?:\"([^\"\r\n]+)\"|'([^'\r\n]+)'|(\$\{[^}]+\}|[^\s,;\"'{}\[\]]+))",
        lambda match: (
            match.group(0)
            if (match.group(2) or match.group(3) or match.group(4)).startswith(("${", "[", "<"))
            else match.group(1)
            + (
                '"${REDACTED_SECRET}"'
                if match.group(2) is not None
                else "'${REDACTED_SECRET}'"
                if match.group(3) is not None
                else "${REDACTED_SECRET}"
            )
        ),
        value,
    )


def make_contract(
    task: str, base: str, constraints: str = "", literals: list[str] | None = None
) -> TaskContract:
    if not task.strip() or not base.strip():
        raise ValueError("Task and base prompt must not be empty.")
    return sanitize(
        {
            "task_description": task.strip(),
            "base_prompt": base.strip(),
            "constraints": constraints.strip(),
            "protected_literals": literals or [],
        }
    )


def guidance_snapshot() -> dict:
    texts = {
        name: (GUIDANCE_DIR / f"{name}.md").read_text(encoding="utf-8")
        for name in ("prompt-customizer", "prompt-engineer")
    }
    return {"version": 1, "texts": texts, "hashes": {name: fingerprint(text) for name, text in texts.items()}}


def guidance_section(snapshot: dict, section: str) -> str:
    sections = []
    for text in snapshot["texts"].values():
        marker = f"## {section} rules\n"
        if marker in text:
            sections.append(text.split(marker, 1)[1].split("\n## ", 1)[0].strip())
    return "\n\n".join(sections)


def parse_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if not match:
            raise ValueError("Expected one JSON value, optionally enclosed in one fence.")
        text = match.group(1)

    def reject_constant(_value: str) -> None:
        raise ValueError("Nonfinite JSON number.")

    return json.loads(text, parse_constant=reject_constant)


def validate_judgment(data: Any) -> dict:
    if not isinstance(data, dict) or set(data) != {*METRICS, "rationale"}:
        raise ValueError("Judge response must contain four metrics and rationale.")
    for metric in METRICS:
        value = data[metric]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 1 <= value <= 10
        ):
            raise ValueError("Judge scores must be finite numbers from 1 to 10.")
    if not isinstance(data["rationale"], str) or not data["rationale"].strip():
        raise ValueError("Judge rationale must be nonempty text.")
    return {**{m: float(data[m]) for m in METRICS}, "rationale": data["rationale"][:1500]}


def validate_variations(data: Any, count: int, contract: TaskContract) -> list[str]:
    if not isinstance(data, list) or not data or len(data) > count:
        raise ValueError("Expected a nonempty candidate array within the requested count.")
    if any(not isinstance(text, str) or not text.strip() for text in data):
        raise ValueError("Candidates must be nonempty strings.")
    result = list(dict.fromkeys(sanitize(text.strip()) for text in data))
    return [text for text in result if all(literal in text for literal in contract["protected_literals"])]


def validate_checks(checks: Any) -> dict:
    if not isinstance(checks, dict) or set(checks) - {
        "required_literals",
        "forbidden_literals",
        "json_schema",
    }:
        raise ValueError("Unknown benchmark checks.")
    for key in ("required_literals", "forbidden_literals"):
        if key in checks and (
            not isinstance(checks[key], list) or any(not isinstance(x, str) or not x for x in checks[key])
        ):
            raise ValueError("Literal checks must be lists of nonempty strings.")
    if "json_schema" in checks:
        Draft202012Validator.check_schema(checks["json_schema"])
        registry = Registry().with_resource(
            "", Resource.from_contents(checks["json_schema"], default_specification=DRAFT202012)
        )

        # Imported schemas must not fetch remote resources during validation.
        def inspect(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in {"$ref", "$dynamicRef"} and isinstance(value, str):
                        if not value.startswith("#"):
                            raise ValueError("Only local JSON Schema references are supported.")
                        try:
                            registry.resolver().lookup(value)
                        except Unresolvable as exc:
                            raise ValueError("Unresolvable local JSON Schema reference.") from exc
                    inspect(value)
            elif isinstance(node, list):
                for value in node:
                    inspect(value)

        inspect(checks["json_schema"])
    return checks


def check_output(output: str, checks: dict) -> list[dict]:
    results = []
    for literal in checks.get("required_literals", []):
        results.append({"check": "required_literal", "literal": literal, "passed": literal in output})
    for literal in checks.get("forbidden_literals", []):
        results.append({"check": "forbidden_literal", "literal": literal, "passed": literal not in output})
    if "json_schema" in checks:
        try:
            value = parse_json(output)
            passed = Draft202012Validator(checks["json_schema"], registry=Registry()).is_valid(value)
        except (ValueError, TypeError, RecursionError, Unresolvable):
            passed = False
        results.append({"check": "json_schema", "passed": passed})
    return results
