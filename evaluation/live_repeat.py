"""
Live-model repeatability experiment.

Runs five fixed gold cases twice against the project's live model adapter
and records:
- model/configuration
- per-run latency
- semantic labels
- label variation between repeated runs
- failures
- available cost information

This experiment is intentionally separate from grader.py because the main
analysis pipeline is idempotent and may reuse persisted results.
"""

from __future__ import annotations

import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.llm.live import OpenAIAdapter
from app.models import Response
from app.analysis.validation import (
    validate_label_consistency,
    validate_model_evidence,
)

ROOT = Path(__file__).resolve().parent
GOLD_FIXTURE = ROOT / "fixtures" / "gold_cases.json"
OUTPUT_FILE = ROOT / "live_repeat_results.json"

CASE_COUNT = 5
RUNS_PER_CASE = 2


def load_gold_cases() -> list[dict[str, Any]]:
    with GOLD_FIXTURE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Support either a direct list or a versioned wrapper.
    if isinstance(data, list):
        cases = data
    elif isinstance(data, dict):
        cases = data.get("cases", [])
    else:
        raise RuntimeError("Unexpected gold fixture format.")

    if len(cases) < CASE_COUNT:
        raise RuntimeError(
            f"Need at least {CASE_COUNT} gold cases; found {len(cases)}."
        )

    return cases[:CASE_COUNT]


def get_response(db, response_id: str) -> Response:
    response = db.execute(
        select(Response).where(
            Response.response_id == response_id
        )
    ).scalar_one_or_none()

    if response is None:
        raise RuntimeError(
            f"Response not found in database: {response_id}"
        )

    return response


def labels(result) -> dict[str, bool]:
    return {
        "mentioned": result.mentioned,
        "recommended": result.recommended,
        "negative": result.negative,
    }


def main() -> None:
    cases = load_gold_cases()
    adapter = OpenAIAdapter()

    db = SessionLocal()

    output: dict[str, Any] = {
        "experiment": "live-model-repeatability",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": adapter.model_name,
        "execution_mode": adapter.execution_mode,
        "configuration": {
            "timeout_seconds": settings.llm_timeout_seconds,
            "max_output_tokens": settings.llm_max_output_tokens,
            "case_count": CASE_COUNT,
            "runs_per_case": RUNS_PER_CASE,
            "total_planned_calls": CASE_COUNT * RUNS_PER_CASE,
        },
        "cost": {
            "status": "unavailable",
            "note": (
                "The adapter does not currently expose provider pricing "
                "or per-request monetary cost. Cost is therefore reported "
                "as unavailable rather than estimated as zero."
            ),
        },
        "cases": [],
    }

    all_latencies: list[float] = []

    try:
        print("=" * 72)
        print("KASPARRO LIVE-MODEL REPEATABILITY CHECK")
        print("=" * 72)
        print(f"Model       : {adapter.model_name}")
        print(f"Cases       : {CASE_COUNT}")
        print(f"Runs/case   : {RUNS_PER_CASE}")
        print(f"Planned calls: {CASE_COUNT * RUNS_PER_CASE}")
        print()

        for index, case in enumerate(cases, start=1):
            case_id = case.get("case_id", f"case-{index}")
            response_id = case["response_id"]

            response = get_response(db, response_id)

            case_result: dict[str, Any] = {
                "case_id": case_id,
                "response_id": response_id,
                "engine": response.engine,
                "runs": [],
            }

            print(
                f"[{index}/{CASE_COUNT}] "
                f"{case_id} | {response.engine} | {response_id}"
            )

            for run_number in range(1, RUNS_PER_CASE + 1):
                started = time.perf_counter()

                try:
                    result = adapter.classify(
                        prompt_text=response.prompt.text,
                        answer_text=response.answer_text,
                    )

                    latency = time.perf_counter() - started
                    all_latencies.append(latency)

                    # Apply the same deterministic validation boundaries
                    # used by the production analysis path.
                    validate_label_consistency(result)
                    validate_model_evidence(
                        result,
                        response.answer_text,
                    )

                    run_result = {
                        "run": run_number,
                        "status": "success",
                        "latency_seconds": round(latency, 3),
                        "labels": labels(result),
                        "recommendation_position": (
                            result.recommendation_position
                        ),
                        "confidence": result.confidence,
                    }

                    print(
                        f"  Run {run_number}: "
                        f"{run_result['labels']} "
                        f"| {latency:.3f}s"
                    )

                except Exception as exc:
                    latency = time.perf_counter() - started
                    all_latencies.append(latency)

                    run_result = {
                        "run": run_number,
                        "status": "failed",
                        "latency_seconds": round(latency, 3),
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }

                    print(
                        f"  Run {run_number}: FAILED "
                        f"| {type(exc).__name__} "
                        f"| {latency:.3f}s"
                    )

                case_result["runs"].append(run_result)

            successful_runs = [
                r
                for r in case_result["runs"]
                if r["status"] == "success"
            ]

            if len(successful_runs) == 2:
                first_labels = successful_runs[0]["labels"]
                second_labels = successful_runs[1]["labels"]

                case_result["exact_label_agreement"] = (
                    first_labels == second_labels
                )

                case_result["label_agreement"] = {
                    label: (
                        first_labels[label]
                        == second_labels[label]
                    )
                    for label in (
                        "mentioned",
                        "recommended",
                        "negative",
                    )
                }

            else:
                case_result["exact_label_agreement"] = None
                case_result["label_agreement"] = None

            output["cases"].append(case_result)
            print()

    finally:
        db.close()

    successful_pairs = [
        case
        for case in output["cases"]
        if case["exact_label_agreement"] is not None
    ]

    exact_agreements = sum(
        1
        for case in successful_pairs
        if case["exact_label_agreement"]
    )

    successful_calls = sum(
        1
        for case in output["cases"]
        for run in case["runs"]
        if run["status"] == "success"
    )

    failed_calls = (
        CASE_COUNT * RUNS_PER_CASE
        - successful_calls
    )

    output["summary"] = {
        "planned_calls": CASE_COUNT * RUNS_PER_CASE,
        "successful_calls": successful_calls,
        "failed_calls": failed_calls,
        "comparable_case_pairs": len(successful_pairs),
        "exact_label_agreement_cases": exact_agreements,
        "exact_label_agreement_rate": (
            round(
                exact_agreements / len(successful_pairs),
                4,
            )
            if successful_pairs
            else None
        ),
        "average_latency_seconds": (
            round(statistics.mean(all_latencies), 3)
            if all_latencies
            else None
        ),
        "median_latency_seconds": (
            round(statistics.median(all_latencies), 3)
            if all_latencies
            else None
        ),
        "min_latency_seconds": (
            round(min(all_latencies), 3)
            if all_latencies
            else None
        ),
        "max_latency_seconds": (
            round(max(all_latencies), 3)
            if all_latencies
            else None
        ),
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(
        f"Successful calls : "
        f"{successful_calls}/{CASE_COUNT * RUNS_PER_CASE}"
    )
    print(
        f"Comparable pairs : {len(successful_pairs)}/{CASE_COUNT}"
    )
    print(
        f"Exact agreement  : "
        f"{exact_agreements}/{len(successful_pairs)}"
        if successful_pairs
        else "Exact agreement  : unavailable"
    )

    if all_latencies:
        print(
            f"Average latency  : "
            f"{statistics.mean(all_latencies):.3f}s"
        )
        print(
            f"Median latency   : "
            f"{statistics.median(all_latencies):.3f}s"
        )

    print("Cost             : unavailable")
    print()
    print(f"Results written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()