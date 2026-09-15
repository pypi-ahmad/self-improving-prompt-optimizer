import copy
import json
import threading
import time

import pytest

from benchmark import builtin_benchmark, validate_benchmark
from contracts import guidance_snapshot, make_contract
from prompts import DEFAULT_BASE_PROMPT, DEFAULT_TASK_DESCRIPTION


class MockProvider:
    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.revision = 0

    def __call__(self, role, settings, payload):
        with self.lock:
            self.calls.append((role, copy.deepcopy(settings), copy.deepcopy(payload)))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.002)
            if role == "generation":
                data = json.loads(payload[-1][1])
                if "parents" in data:
                    with self.lock:
                        self.revision += 1
                        revision = self.revision
                    text = json.dumps(
                        [
                            f"{data['original_contract']['base_prompt']} Revision {revision}-{i}."
                            for i in range(data["count"])
                        ]
                    )
                else:
                    text = json.dumps(
                        {
                            split: [
                                {
                                    "id": f"{split}-{i}",
                                    "input": f"{split} input {i}",
                                    "guideline": "Preserve the input.",
                                    "checks": {},
                                }
                                for i in range(data[f"{split}_count"])
                            ]
                            for split in ("optimization", "holdout")
                        }
                    )
            elif role == "judge":
                data = json.loads(payload[-1][1])
                score = 8.0 if "Revision" in data["candidate_as_data"] else 7.0
                text = json.dumps(
                    {
                        "accuracy": score,
                        "clarity": score,
                        "conciseness": score,
                        "helpfulness": score,
                        "rationale": "Preserves the supplied input.",
                    }
                )
            elif role == "embedding":
                return {
                    "vectors": [[float(i + 1), 1.0] for i in range(len(payload))],
                    "usage": {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 0},
                }
            else:
                text = payload[-1][1]
            return {
                "text": text,
                "finish_reason": "stop",
                "usage": {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 20},
            }
        finally:
            with self.lock:
                self.active -= 1


@pytest.fixture
def provider():
    return MockProvider()


@pytest.fixture
def contract():
    return make_contract(DEFAULT_TASK_DESCRIPTION, DEFAULT_BASE_PROMPT)


@pytest.fixture
def guidance():
    return guidance_snapshot()


@pytest.fixture
def bundle(contract):
    data = builtin_benchmark(contract)
    return validate_benchmark(
        {"optimization": data["optimization"][:2], "holdout": data["holdout"][:2]}, contract
    )
