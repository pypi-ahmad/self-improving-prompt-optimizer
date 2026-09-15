"""Explicit, versioned browser exports; application runs remain in memory."""

import csv
import io
import json

from contracts import METRICS, sanitize


def history_rows(state):
    return [
        {
            "generation": row["generation"],
            "source": row["source"],
            "prompt": row["prompt"],
            "status": row["status"],
            "eligible": row["eligible"],
            "weighted_score": row["weighted_score"],
            **{m: row["metrics"][m] if row["metrics"] else None for m in METRICS},
            "cross_case_spread": row["cross_case_spread"],
        }
        for row in state.get("history", [])
    ]


def history_csv(state):
    rows = history_rows(state)
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return buf.getvalue()


def export_run(state, runtime):
    return json.dumps(
        sanitize(
            {
                "schema_version": 1,
                "run": state,
                "usage": runtime.snapshot(),
                "prices_per_million_tokens": runtime.prices,
                "price_source": "user-configured",
                "concurrency": runtime.concurrency,
            }
        ),
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
