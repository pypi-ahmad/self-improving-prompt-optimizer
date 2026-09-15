"""Provider calls with one thread-safe allowance, including retries and preparation."""

import copy
import json
import math
import os
import threading
import time
import uuid
from pathlib import Path

from openai import OpenAI

from contracts import sanitize

LUNA = "gpt-5.6-luna"
TERRA = "gpt-5.6-terra"
PRICES = {
    LUNA: {"input": 0.20, "cached_input": 0.02, "output": 1.20},
    TERRA: {"input": 2.00, "cached_input": 0.20, "output": 12.00},
}


def default_models() -> dict:
    return {
        "generation": {
            "model": LUNA,
            "reasoning_effort": "medium",
            "temperature": None,
            "max_completion_tokens": 8192,
        },
        "candidate": {
            "model": LUNA,
            "reasoning_effort": "medium",
            "temperature": None,
            "max_completion_tokens": 4096,
        },
        "judge": {
            "model": TERRA,
            "reasoning_effort": "medium",
            "temperature": None,
            "max_completion_tokens": 4096,
        },
    }


class BudgetExceeded(Exception):
    """No new request can fit within the remaining allowance."""


def input_upper_bound(messages) -> int:
    # A text token cannot contain less than one UTF-8 byte. Allow extra framing
    # per message; reserve at uncached rates even if the provider later reports a hit.
    return len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) + 512 * (len(messages) + 1)


def safe_error(exc: Exception) -> dict:
    status = getattr(exc, "status_code", None)
    return {"type": type(exc).__name__, "status_code": status if isinstance(status, int) else None}


class Runtime:
    def __init__(
        self,
        models=None,
        prices=None,
        usd_cap=6.0,
        call_cap=1000,
        concurrency=4,
        adapter=None,
        ledger_path: Path | None = None,
    ):
        if not math.isfinite(usd_cap) or usd_cap <= 0 or not 1 <= concurrency <= 8 or call_cap < 1:
            raise ValueError("Invalid budget or concurrency configuration.")
        self.models = copy.deepcopy(models or default_models())
        if set(self.models) != {"generation", "candidate", "judge"}:
            raise ValueError("Configure generation, candidate, and judge models.")
        self.prices = copy.deepcopy(PRICES if prices is None else prices)
        for setting in self.models.values():
            if not isinstance(setting["model"], str) or not setting["model"].strip():
                raise ValueError("Model IDs must not be empty.")
            if (
                type(setting["max_completion_tokens"]) is not int
                or not 1 <= setting["max_completion_tokens"] <= 32768
            ):
                raise ValueError("Completion limits must be between 1 and 32768.")
            if setting.get("reasoning_effort") not in {None, "none", "low", "medium", "high"}:
                raise ValueError("Unsupported reasoning effort setting.")
            temp = setting.get("temperature")
            if temp is not None and (not math.isfinite(temp) or not 0 <= temp <= 2):
                raise ValueError("Invalid temperature.")
            self._rates(setting["model"])
        if type(call_cap) is not int or type(concurrency) is not int:
            raise ValueError("Call and concurrency limits must be integers.")
        self.usd_cap, self.call_cap, self.concurrency = float(usd_cap), call_cap, concurrency
        self.adapter = adapter
        self.ledger_path = ledger_path
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(concurrency)
        self.events: list[dict] = []
        self.run_id = str(uuid.uuid4())
        self.started_at = time.time()
        self.halted = False
        self.clients = {}
        if ledger_path and ledger_path.exists():
            previous = json.loads(ledger_path.read_text(encoding="utf-8"))
            if previous["usd_cap"] != usd_cap or previous["call_cap"] != call_cap:
                raise ValueError("Existing verification ledger has different limits.")
            self.events = previous["events"]
            self.run_id = previous["run_id"]
            self.started_at = previous["started_at"]
            self.halted = previous.get("halted", False)

    def _rates(self, model):
        rates = self.prices.get(model)
        if not isinstance(rates, dict) or set(rates) != {"input", "cached_input", "output"}:
            raise ValueError(f"Configure input, cached input, and output prices for {model}.")
        if any(
            isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0
            for x in rates.values()
        ):
            raise ValueError("Model prices must be finite nonnegative numbers.")
        return rates

    def estimate(self, role, messages, output_limit=None):
        settings = self.models[role]
        rates = self._rates(settings["model"])
        cap = settings["max_completion_tokens"] if output_limit is None else output_limit
        return (input_upper_bound(messages) * rates["input"] + cap * rates["output"]) / 1_000_000

    def _snapshot_unlocked(self):
        charged = sum(e["charged_usd"] for e in self.events)
        reported = sum(e["charged_usd"] for e in self.events if e["accounting"] == "reported")
        grouped = {}
        for event in self.events:
            key = (event["model"], event["phase"])
            row = grouped.setdefault(
                key,
                {
                    "model": key[0],
                    "phase": key[1],
                    "calls": 0,
                    "failures": 0,
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "estimated_usd": 0.0,
                    "latency_seconds": 0.0,
                    "unreported_calls": 0,
                },
            )
            row["calls"] += 1
            row["failures"] += event["status"] == "failed"
            row["unreported_calls"] += event["accounting"] != "reported"
            for metric in ("input_tokens", "cached_input_tokens", "output_tokens"):
                row[metric] += event[metric] or 0
            row["estimated_usd"] += event["charged_usd"]
            row["latency_seconds"] += event["latency_seconds"] or 0
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "usd_cap": self.usd_cap,
            "call_cap": self.call_cap,
            "calls": len(self.events),
            "charged_usd": charged,
            "reported_usd": reported,
            "reserved_usd": charged - reported,
            "remaining_usd": max(0, self.usd_cap - charged),
            "halted": self.halted,
            "elapsed_seconds": time.time() - self.started_at,
            "by_model_phase": list(grouped.values()),
            "events": copy.deepcopy(self.events),
        }

    def snapshot(self):
        with self.lock:
            return self._snapshot_unlocked()

    def _save(self):
        if self.ledger_path:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.ledger_path.with_suffix(".tmp")
            temp.write_text(
                json.dumps(self._snapshot_unlocked(), indent=2, allow_nan=False), encoding="utf-8"
            )
            temp.replace(self.ledger_path)

    def can_afford(self, cost, calls=1):
        with self.lock:
            return (
                not self.halted
                and len(self.events) + calls <= self.call_cap
                and sum(e["charged_usd"] for e in self.events) + cost <= self.usd_cap
            )

    def _reserve(self, role, phase, model, estimate, attempt):
        with self.lock:
            if not self.can_afford(estimate):
                raise BudgetExceeded("Call or USD allowance exhausted.")
            event = {
                "id": len(self.events) + 1,
                "role": role,
                "phase": phase,
                "model": model,
                "attempt": attempt,
                "status": "pending",
                "accounting": "reserved",
                "charged_usd": estimate,
                "reservation_usd": estimate,
                "input_tokens": None,
                "cached_input_tokens": None,
                "output_tokens": None,
                "latency_seconds": None,
                "error": None,
            }
            self.events.append(event)
            self._save()
            return event

    def _settle(self, event, response, latency, error=None):
        with self.lock:
            event.update(status="failed" if error else "complete", latency_seconds=latency, error=error)
            usage = response.get("usage") if response else None
            if usage:
                values = [
                    usage.get("input_tokens"),
                    usage.get("cached_input_tokens", 0),
                    usage.get("output_tokens"),
                ]
                if (
                    all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in values)
                    and values[1] <= values[0]
                ):
                    inp, cached, out = values
                    rates = self._rates(event["model"])
                    actual = (
                        (inp - cached) * rates["input"]
                        + cached * rates["cached_input"]
                        + out * rates["output"]
                    ) / 1_000_000
                    event.update(
                        input_tokens=inp,
                        cached_input_tokens=cached,
                        output_tokens=out,
                        charged_usd=actual,
                        accounting="reported",
                    )
                    if actual > event["reservation_usd"] + 1e-9:
                        self.halted = True
            self._save()

    def _client(self, model):
        if model == "agnes-2.5-flash":
            key_name, base_url = "AGNES_API_KEY", "https://apihub.agnes-ai.com/v1"
        else:
            key_name, base_url = "OPENAI_API_KEY", os.environ.get("OPENAI_BASE_URL") or None
        with self.lock:
            client_key = (key_name, base_url)
            if client_key not in self.clients:
                if not os.environ.get(key_name):
                    raise ValueError(f"Missing {key_name}.")
                self.clients[client_key] = OpenAI(
                    api_key=os.environ[key_name], base_url=base_url, max_retries=0, timeout=60
                )
            return self.clients[client_key]

    def _provider(self, role, setting, payload):
        client = self._client(setting["model"])
        if role == "embedding":
            result = client.embeddings.create(model=setting["model"], input=payload)
            return {
                "vectors": [item.embedding for item in result.data],
                "usage": {
                    "input_tokens": result.usage.prompt_tokens,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                },
            }
        kwargs = {
            "model": setting["model"],
            "messages": [
                {"role": "user" if role_name == "human" else role_name, "content": text}
                for role_name, text in payload
            ],
            "max_completion_tokens": setting["max_completion_tokens"],
        }
        if setting.get("reasoning_effort") is not None:
            kwargs["reasoning_effort"] = setting["reasoning_effort"]
        if setting.get("temperature") is not None:
            kwargs["temperature"] = setting["temperature"]
        if setting["model"] in {LUNA, TERRA}:
            kwargs["service_tier"] = "default"
        result = client.chat.completions.create(**kwargs)
        choice = result.choices[0]
        usage = None
        if result.usage:
            details = result.usage.prompt_tokens_details
            usage = {
                "input_tokens": result.usage.prompt_tokens,
                "cached_input_tokens": (details.cached_tokens or 0) if details else 0,
                "output_tokens": result.usage.completion_tokens,
            }
        return {"text": choice.message.content or "", "usage": usage, "finish_reason": choice.finish_reason}

    def _dispatch(self, role, phase, setting, payload, estimate):
        for attempt in (1, 2):
            with self.slots:
                event = self._reserve(role, phase, setting["model"], estimate, attempt)
                start = time.perf_counter()
                try:
                    response = (self.adapter or self._provider)(role, setting, payload)
                except Exception as exc:  # noqa: BLE001 - account for every failed provider attempt.
                    error = safe_error(exc)
                    self._settle(event, None, time.perf_counter() - start, error)
                    transient = (
                        error["status_code"] == 429
                        or (error["status_code"] or 0) >= 500
                        or error["type"] in {"APIConnectionError", "APITimeoutError", "TimeoutError"}
                    )
                    if not transient or attempt == 2:
                        return {"status": "failed", "error": error, "usage_id": event["id"]}
                else:
                    incomplete = response.get("finish_reason", "stop") != "stop"
                    error = {"type": "IncompleteResponse", "status_code": None} if incomplete else None
                    self._settle(event, response, time.perf_counter() - start, error)
                    if incomplete:
                        return {
                            "status": "failed",
                            "error": {"type": "IncompleteResponse", "status_code": None},
                            "usage_id": event["id"],
                        }
                    return {
                        **response,
                        "text": sanitize(response.get("text", "")),
                        "status": "complete",
                        "usage_id": event["id"],
                    }
            time.sleep(0.25)
        raise AssertionError("Unreachable retry state")

    def call(self, role, messages, phase):
        payload = [(kind, sanitize(text)) for kind, text in messages]
        try:
            return self._dispatch(role, phase, self.models[role], payload, self.estimate(role, payload))
        except BudgetExceeded:
            return {
                "status": "budget_skipped",
                "error": {"type": "BudgetExceeded", "status_code": None},
                "usage_id": None,
            }

    def embed(self, texts, model="text-embedding-3-small"):
        if model not in self.prices:
            return {"status": "unpriced", "vectors": None}
        payload = sanitize(texts)
        rates = self._rates(model)
        estimate = input_upper_bound(payload) * rates["input"] / 1_000_000
        try:
            return self._dispatch("embedding", "diversity", {"model": model}, payload, estimate)
        except BudgetExceeded:
            return {"status": "budget_skipped", "vectors": None}
