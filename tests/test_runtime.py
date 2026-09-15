import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from runtime import LUNA, Runtime


def test_concurrent_allowance_and_accounting(provider):
    runtime = Runtime(adapter=provider, call_cap=5, concurrency=2)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: runtime.call("candidate", [("human", "hello")], "test"), range(12)))
    assert runtime.snapshot()["calls"] == 5
    assert sum(r["status"] == "budget_skipped" for r in results) == 7
    assert provider.max_active == 2
    expected = (80 * 0.20 + 20 * 0.02 + 20 * 1.20) / 1_000_000
    assert runtime.snapshot()["charged_usd"] == pytest.approx(expected * 5)


def test_dollar_reservations_and_missing_usage():
    def no_usage(*_args):
        return {"text": "done"}

    runtime = Runtime(adapter=no_usage, usd_cap=0.01)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: runtime.call("candidate", [("human", "hello")], "test"), range(8)))
    assert runtime.snapshot()["charged_usd"] <= 0.01
    assert any(r["status"] == "budget_skipped" for r in results)
    assert runtime.snapshot()["reported_usd"] == 0
    assert all(e["accounting"] == "reserved" for e in runtime.snapshot()["events"])


def test_retry_and_sanitized_failures():
    class Transient(Exception):
        status_code = 429

    def fails(*_args):
        raise Transient("api_key=do-not-show-this")

    runtime = Runtime(adapter=fails)
    result = runtime.call("judge", [("human", "hello")], "test")
    assert result["status"] == "failed"
    assert runtime.snapshot()["calls"] == 2
    assert "do-not-show-this" not in json.dumps(runtime.snapshot())


def test_verification_ledger_survives_restart(tmp_path, provider):
    path = tmp_path / "ledger.json"
    first = Runtime(adapter=provider, ledger_path=path, call_cap=1)
    first.call("candidate", [("human", "hello")], "test")
    second = Runtime(adapter=provider, ledger_path=path, call_cap=1)
    assert second.call("candidate", [("human", "hello")], "test")["status"] == "budget_skipped"
    assert second.snapshot()["run_id"] == first.snapshot()["run_id"]


def test_pricing_and_completion_failure(provider):
    with pytest.raises(ValueError):
        Runtime(prices={})
    runtime = Runtime(adapter=lambda *_: {"text": "partial", "finish_reason": "length"})
    assert runtime.call("candidate", [("human", "x")], "test")["status"] == "failed"
    assert runtime.embed(["x"])["status"] == "unpriced"
    assert runtime.models["candidate"]["model"] == LUNA


def test_provider_request_parameters(monkeypatch):
    observed = []

    def create(**kwargs):
        observed.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=20, completion_tokens=10, prompt_tokens_details=None),
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    runtime = Runtime()
    monkeypatch.setattr(runtime, "_client", lambda _: client)
    runtime.call("judge", [("system", "Judge"), ("human", "Input")], "test")
    assert observed[0]["model"] == "gpt-5.6-terra"
    assert observed[0]["reasoning_effort"] == "medium"
    assert "temperature" not in observed[0]
    assert observed[0]["max_completion_tokens"] == 4096
    assert observed[0]["service_tier"] == "default"
    assert observed[0]["messages"][1]["role"] == "user"


def test_reported_overrun_halts_dispatch():
    runtime = Runtime(
        adapter=lambda *_: {
            "text": "ok",
            "usage": {"input_tokens": 10_000_000, "cached_input_tokens": 0, "output_tokens": 0},
        }
    )
    runtime.call("candidate", [("human", "x")], "test")
    assert runtime.snapshot()["halted"]
    assert runtime.call("candidate", [("human", "x")], "test")["status"] == "budget_skipped"
