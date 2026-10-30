import json
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.analysis.scoring import calculate_visibility_score
from app.analysis.validation import (
    validate_label_consistency,
    validate_model_evidence,
)
from app.db import SessionLocal
from app.llm.base import InvalidModelOutputError
from app.llm.replay import ReplayAdapter
from app.models import AnalysisResult, AnalysisRun, Response
from app.schemas import ModelAnalysisOutput


ROOT = Path(__file__).resolve().parent
GOLD_FIXTURE = ROOT / "fixtures" / "gold_cases.json"
SYNTHETIC_FIXTURE = ROOT / "fixtures" / "synthetic_cases.json"

LIVE_ANALYSIS_ID = "analysis:2f8298d6-d3d0-4ed7-a201-089369d1e273"

LABELS = ("mentioned", "recommended", "negative")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def percentage(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def print_heading(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def print_subheading(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def calculate_label_metrics(
    expected_rows: list[dict[str, bool]],
    predicted_rows: list[dict[str, bool]],
) -> dict[str, dict[str, float | int]]:
    metrics: dict[str, dict[str, float | int]] = {}

    for label in LABELS:
        tp = 0
        fp = 0
        fn = 0
        tn = 0

        for expected, predicted in zip(expected_rows, predicted_rows):
            expected_value = bool(expected[label])
            predicted_value = bool(predicted[label])

            if expected_value and predicted_value:
                tp += 1
            elif not expected_value and predicted_value:
                fp += 1
            elif expected_value and not predicted_value:
                fn += 1
            else:
                tn += 1

        total = tp + fp + fn + tn

        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        agreement = (tp + tn) / total if total else 0.0

        metrics[label] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "agreement": round(agreement, 3),
        }

    return metrics


def print_metrics(
    title: str,
    metrics: dict[str, dict[str, float | int]],
) -> None:
    print_subheading(title)

    print(
        f"{'Label':<16}"
        f"{'Precision':>12}"
        f"{'Recall':>10}"
        f"{'Agreement':>12}"
        f"{'TP':>6}"
        f"{'FP':>6}"
        f"{'FN':>6}"
    )

    for label in LABELS:
        row = metrics[label]

        print(
            f"{label:<16}"
            f"{row['precision']:>12.3f}"
            f"{row['recall']:>10.3f}"
            f"{row['agreement']:>12.3f}"
            f"{row['tp']:>6}"
            f"{row['fp']:>6}"
            f"{row['fn']:>6}"
        )


def get_live_analysis_run(db) -> AnalysisRun:
    analysis_run = db.execute(
        select(AnalysisRun).where(
            AnalysisRun.analysis_id == LIVE_ANALYSIS_ID
        )
    ).scalar_one_or_none()

    if analysis_run is None:
        raise RuntimeError(
            f"Live analysis run not found: {LIVE_ANALYSIS_ID}"
        )

    return analysis_run


def get_response_by_response_id(
    db,
    response_id: str,
) -> Response | None:
    return db.execute(
        select(Response).where(
            Response.response_id == response_id
        )
    ).scalar_one_or_none()


def get_analysis_result(
    db,
    analysis_run: AnalysisRun,
    response: Response,
) -> AnalysisResult | None:
    """
    AnalysisResult.response_db_id is the internal foreign key
    pointing to Response.id.

    AnalysisResult.response_id is the external response UUID.
    """

    return db.execute(
        select(AnalysisResult).where(
            AnalysisResult.analysis_run_id == analysis_run.id,
            AnalysisResult.response_db_id == response.id,
        )
    ).scalar_one_or_none()


def evaluate_live_gold_cases(
    gold_cases: list[dict[str, Any]],
) -> None:
    print_heading("1. LIVE LLM GOLD-SET EVALUATION")

    expected_rows: list[dict[str, bool]] = []
    predicted_rows: list[dict[str, bool]] = []

    missing = 0
    non_success = 0

    db = SessionLocal()

    try:
        analysis_run = get_live_analysis_run(db)

        print(f"Analysis ID : {analysis_run.analysis_id}")
        print(f"Cases       : {len(gold_cases)}")

        for case in gold_cases:
            response = get_response_by_response_id(
                db,
                case["response_id"],
            )

            if response is None:
                missing += 1
                print(
                    f"[MISSING] {case['case_id']} "
                    f"{case['response_id']}"
                )
                continue

            result = get_analysis_result(
                db,
                analysis_run,
                response,
            )

            if result is None:
                missing += 1
                print(
                    f"[NO RESULT] {case['case_id']} "
                    f"{case['response_id']}"
                )
                continue

            if result.status != "success":
                non_success += 1
                print(
                    f"[{result.status.upper()}] "
                    f"{case['case_id']} "
                    f"{case['response_id']}"
                )
                continue

            expected = {
                label: bool(case["expected"][label])
                for label in LABELS
            }

            predicted = {
                "mentioned": bool(result.mentioned),
                "recommended": bool(result.recommended),
                "negative": bool(result.negative),
            }

            expected_rows.append(expected)
            predicted_rows.append(predicted)

            exact_match = expected == predicted
            marker = "PASS" if exact_match else "DIFF"

            print(
                f"[{marker}] "
                f"{case['case_id']} "
                f"{case['engine']:<8} "
                f"{case['category']:<9} "
                f"expected={expected} "
                f"predicted={predicted}"
            )

        evaluated = len(expected_rows)
        coverage = percentage(evaluated, len(gold_cases))

        print()
        print(f"Evaluated successfully : {evaluated}")
        print(f"Non-success results    : {non_success}")
        print(f"Missing results        : {missing}")
        print(f"Evaluation coverage    : {coverage}%")

        if expected_rows:
            metrics = calculate_label_metrics(
                expected_rows,
                predicted_rows,
            )

            print_metrics(
                "Per-label metrics",
                metrics,
            )

            exact_matches = sum(
                1
                for expected, predicted in zip(
                    expected_rows,
                    predicted_rows,
                )
                if expected == predicted
            )

            exact_pct = percentage(
                exact_matches,
                evaluated,
            )

            print()
            print(
                f"Exact case agreement   : "
                f"{exact_matches}/{evaluated} "
                f"({exact_pct}%)"
            )

    finally:
        db.close()


def evaluate_replay_baseline(
    gold_cases: list[dict[str, Any]],
) -> None:
    print_heading("2. DETERMINISTIC REPLAY BASELINE")

    adapter = ReplayAdapter()

    expected_rows: list[dict[str, bool]] = []
    predicted_rows: list[dict[str, bool]] = []

    missing = 0

    db = SessionLocal()

    try:
        for case in gold_cases:
            response = get_response_by_response_id(
                db,
                case["response_id"],
            )

            if response is None:
                missing += 1
                continue

            output = adapter.classify(
                prompt_text=response.prompt.text,
                answer_text=response.answer_text,
            )

            expected = {
                label: bool(case["expected"][label])
                for label in LABELS
            }

            predicted = {
                "mentioned": bool(output.mentioned),
                "recommended": bool(output.recommended),
                "negative": bool(output.negative),
            }

            expected_rows.append(expected)
            predicted_rows.append(predicted)

            exact_match = expected == predicted
            marker = "PASS" if exact_match else "DIFF"

            print(
                f"[{marker}] "
                f"{case['case_id']} "
                f"expected={expected} "
                f"predicted={predicted}"
            )

        evaluated = len(expected_rows)

        print()
        print(f"Evaluated              : {evaluated}")
        print(f"Missing responses      : {missing}")

        if expected_rows:
            metrics = calculate_label_metrics(
                expected_rows,
                predicted_rows,
            )

            print_metrics(
                "Baseline per-label metrics",
                metrics,
            )

            exact_matches = sum(
                1
                for expected, predicted in zip(
                    expected_rows,
                    predicted_rows,
                )
                if expected == predicted
            )

            exact_pct = percentage(
                exact_matches,
                evaluated,
            )

            print()
            print(
                f"Exact case agreement   : "
                f"{exact_matches}/{evaluated} "
                f"({exact_pct}%)"
            )

    finally:
        db.close()


def build_output(
    *,
    mentioned: bool,
    recommended: bool,
    negative: bool,
    recommendation_position: int | None = None,
    evidence: list[dict[str, str]] | None = None,
) -> ModelAnalysisOutput:
    payload = {
        "mentioned": mentioned,
        "recommended": recommended,
        "negative": negative,
        "recommendation_position": recommendation_position,
        "competitors": [],
        "evidence": evidence or [],
        "confidence": 1.0,
    }

    return ModelAnalysisOutput.model_validate(payload)


def evaluate_scoring() -> None:
    print_heading("3. DETERMINISTIC SCORE VERIFICATION")

    cases = [
        {
            "name": "absent",
            "result": build_output(
                mentioned=False,
                recommended=False,
                negative=False,
            ),
            "citation": False,
            "expected_score": 0,
        },
        {
            "name": "mention_only",
            "result": build_output(
                mentioned=True,
                recommended=False,
                negative=False,
            ),
            "citation": False,
            "expected_score": 30,
        },
        {
            "name": "recommendation",
            "result": build_output(
                mentioned=True,
                recommended=True,
                negative=False,
            ),
            "citation": False,
            "expected_score": 70,
        },
        {
            "name": "recommended_position_1",
            "result": build_output(
                mentioned=True,
                recommended=True,
                negative=False,
                recommendation_position=1,
            ),
            "citation": False,
            "expected_score": 90,
        },
        {
            "name": "recommended_position_2",
            "result": build_output(
                mentioned=True,
                recommended=True,
                negative=False,
                recommendation_position=2,
            ),
            "citation": False,
            "expected_score": 85,
        },
        {
            "name": "recommended_position_3",
            "result": build_output(
                mentioned=True,
                recommended=True,
                negative=False,
                recommendation_position=3,
            ),
            "citation": False,
            "expected_score": 80,
        },
        {
            "name": "mention_with_citation",
            "result": build_output(
                mentioned=True,
                recommended=False,
                negative=False,
            ),
            "citation": True,
            "expected_score": 40,
        },
        {
            "name": "negative_mention",
            "result": build_output(
                mentioned=True,
                recommended=False,
                negative=True,
            ),
            "citation": False,
            "expected_score": 0,
        },
        {
            "name": "maximum",
            "result": build_output(
                mentioned=True,
                recommended=True,
                negative=False,
                recommendation_position=1,
            ),
            "citation": True,
            "expected_score": 100,
        },
    ]

    passed = 0

    for case in cases:
        actual = calculate_visibility_score(
            case["result"],
            has_kasparro_citation=case["citation"],
        )

        success = actual == case["expected_score"]

        if success:
            passed += 1

        marker = "PASS" if success else "FAIL"

        print(
            f"[{marker}] "
            f"{case['name']:<24} "
            f"expected={case['expected_score']:<3} "
            f"actual={actual}"
        )

    print()
    print(
        f"Score verification     : "
        f"{passed}/{len(cases)} passed"
    )


def evaluate_validation() -> None:
    print_heading("4. MODEL OUTPUT VALIDATION")

    checks: list[tuple[str, bool]] = []

    answer = "Kasparro is an AI visibility platform."

    valid_result = build_output(
        mentioned=True,
        recommended=False,
        negative=False,
        evidence=[
            {
                "quote": "Kasparro is an AI visibility platform.",
                "label": "mentioned",
            }
        ],
    )

    try:
        validate_model_evidence(
            valid_result,
            answer,
        )
        checks.append(
            ("valid evidence accepted", True)
        )
    except Exception:
        checks.append(
            ("valid evidence accepted", False)
        )

    unsupported_result = build_output(
        mentioned=True,
        recommended=True,
        negative=False,
        evidence=[
            {
                "quote": (
                    "Kasparro is the best enterprise "
                    "AI visibility platform."
                ),
                "label": "recommended",
            }
        ],
    )

    try:
        validate_model_evidence(
            unsupported_result,
            answer,
        )
        checks.append(
            ("unsupported evidence rejected", False)
        )
    except InvalidModelOutputError:
        checks.append(
            ("unsupported evidence rejected", True)
        )

    inconsistent_result = build_output(
        mentioned=False,
        recommended=True,
        negative=False,
    )

    try:
        validate_label_consistency(
            inconsistent_result
        )
        checks.append(
            (
                "recommendation without mention rejected",
                False,
            )
        )
    except InvalidModelOutputError:
        checks.append(
            (
                "recommendation without mention rejected",
                True,
            )
        )

    invalid_position = build_output(
        mentioned=True,
        recommended=False,
        negative=False,
        recommendation_position=1,
    )

    try:
        validate_label_consistency(
            invalid_position
        )
        checks.append(
            (
                "position without recommendation rejected",
                False,
            )
        )
    except InvalidModelOutputError:
        checks.append(
            (
                "position without recommendation rejected",
                True,
            )
        )

    passed = 0

    for name, success in checks:
        if success:
            passed += 1

        marker = "PASS" if success else "FAIL"
        print(f"[{marker}] {name}")

    print()
    print(
        f"Validation checks      : "
        f"{passed}/{len(checks)} passed"
    )


def evaluate_synthetic_cases(
    synthetic_cases: list[dict[str, Any]],
) -> None:
    print_heading("5. SYNTHETIC EDGE CASES")

    adapter = ReplayAdapter()

    passed = 0
    evaluated = 0

    for case in synthetic_cases:
        name = case["name"]

        if name == "empty_response":
            success = case["answer"].strip() == ""

            evaluated += 1
            passed += int(success)

            marker = "PASS" if success else "FAIL"

            print(
                f"[{marker}] "
                f"{case['case_id']} "
                f"empty response -> skipped"
            )

            continue

        if name == "unsupported_evidence":
            model_output = case[
                "model_output_under_test"
            ]

            evidence_items = []

            for label_name, quotes in model_output[
                "evidence"
            ].items():
                for quote in quotes:
                    evidence_items.append(
                        {
                            "quote": quote,
                            "label": label_name,
                        }
                    )

            result = build_output(
                mentioned=model_output["mentioned"],
                recommended=model_output["recommended"],
                negative=model_output["negative"],
                evidence=evidence_items,
            )

            try:
                validate_model_evidence(
                    result,
                    case["answer"],
                )
                success = False
            except InvalidModelOutputError:
                success = True

            evaluated += 1
            passed += int(success)

            marker = "PASS" if success else "FAIL"

            print(
                f"[{marker}] "
                f"{case['case_id']} "
                f"unsupported evidence rejected"
            )

            continue

        output = adapter.classify(
            prompt_text=case["prompt"],
            answer_text=case["answer"],
        )

        expected = case["expected"]

        success = (
            output.mentioned == expected["mentioned"]
            and output.recommended == expected["recommended"]
            and output.negative == expected["negative"]
        )

        evaluated += 1
        passed += int(success)

        marker = "PASS" if success else "FAIL"

        print(
            f"[{marker}] "
            f"{case['case_id']} "
            f"mentioned={output.mentioned} "
            f"recommended={output.recommended} "
            f"negative={output.negative}"
        )

    print()
    print(
        f"Synthetic checks       : "
        f"{passed}/{evaluated} passed"
    )


def evaluate_analysis_accounting() -> None:
    print_heading("6. ANALYSIS ACCOUNTING")

    db = SessionLocal()

    try:
        analysis_run = get_live_analysis_run(db)

        results = db.execute(
            select(AnalysisResult).where(
                AnalysisResult.analysis_run_id
                == analysis_run.id
            )
        ).scalars().all()

        success = sum(
            1
            for result in results
            if result.status == "success"
        )

        failed = sum(
            1
            for result in results
            if result.status == "failed"
        )

        skipped = sum(
            1
            for result in results
            if result.status == "skipped"
        )

        accounted = success + failed + skipped
        total = len(results)

        coverage = percentage(
            success,
            total,
        )

        print(f"Total results          : {total}")
        print(f"Success                : {success}")
        print(f"Failed                 : {failed}")
        print(f"Skipped                : {skipped}")
        print(f"Accounted              : {accounted}")
        print(f"Coverage               : {coverage}%")

        if accounted == total:
            print(
                "[PASS] Every analysis result "
                "is accounted for."
            )
        else:
            print(
                "[FAIL] Some analysis results "
                "are not in a terminal state."
            )

        failed_scores = [
            result.visibility_score
            for result in results
            if result.status == "failed"
        ]

        if all(
            score is None
            for score in failed_scores
        ):
            print(
                "[PASS] Failed analyses are not "
                "converted into zero visibility scores."
            )
        else:
            print(
                "[FAIL] At least one failed analysis "
                "has a visibility score."
            )

    finally:
        db.close()


def evaluate_fixture_distribution(
    gold_cases: list[dict[str, Any]],
) -> None:
    print_heading("7. GOLD FIXTURE DISTRIBUTION")

    engines: dict[str, int] = {}
    categories: dict[str, int] = {}

    for case in gold_cases:
        engine = case["engine"]
        category = case["category"]

        engines[engine] = engines.get(
            engine,
            0,
        ) + 1

        categories[category] = categories.get(
            category,
            0,
        ) + 1

    print("Engines:")

    for engine, count in sorted(
        engines.items()
    ):
        print(f"  {engine:<10} {count}")

    print()
    print("Categories:")

    for category, count in sorted(
        categories.items()
    ):
        print(f"  {category:<10} {count}")

    has_three_engines = len(engines) >= 3
    has_multiple_categories = len(categories) >= 2
    enough_cases = len(gold_cases) >= 12

    print()

    marker = "PASS" if enough_cases else "FAIL"
    print(
        f"[{marker}] "
        "At least 12 supplied responses manually labelled."
    )

    marker = (
        "PASS"
        if has_three_engines
        else "FAIL"
    )
    print(
        f"[{marker}] "
        "Gold set spans at least three engines."
    )

    marker = (
        "PASS"
        if has_multiple_categories
        else "FAIL"
    )
    print(
        f"[{marker}] "
        "Gold set spans multiple prompt categories."
    )


def main() -> None:
    gold_fixture = load_json(
        GOLD_FIXTURE
    )

    synthetic_fixture = load_json(
        SYNTHETIC_FIXTURE
    )

    gold_cases = gold_fixture["cases"]
    synthetic_cases = synthetic_fixture["cases"]

    print()
    print("KASPARRO AI VISIBILITY EVALUATION")
    print("AI interprets. Code decides.")
    print(
        f"Gold fixture      : "
        f"{gold_fixture['fixture_version']}"
    )
    print(
        f"Synthetic fixture : "
        f"{synthetic_fixture['fixture_version']}"
    )
    print(
        f"Gold cases        : "
        f"{len(gold_cases)}"
    )
    print(
        f"Synthetic cases   : "
        f"{len(synthetic_cases)}"
    )

    evaluate_live_gold_cases(
        gold_cases
    )

    evaluate_replay_baseline(
        gold_cases
    )

    evaluate_scoring()

    evaluate_validation()

    evaluate_synthetic_cases(
        synthetic_cases
    )

    evaluate_analysis_accounting()

    evaluate_fixture_distribution(
        gold_cases
    )

    print_heading("EVALUATION COMPLETE")

    print(
        "The report above compares the persisted live semantic "
        "analysis against manually labelled supplied responses, "
        "compares the deterministic replay baseline on the same "
        "cases, verifies score calculation, exercises validation "
        "boundaries, checks synthetic edge cases, and confirms "
        "terminal-result accounting."
    )


if __name__ == "__main__":
    main()