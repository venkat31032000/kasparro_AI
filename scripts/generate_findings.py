import json
from collections import defaultdict

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    AnalysisResult,
    AnalysisRun,
    Prompt,
    Response,
)


def prompt_group(prompt_id: str) -> str:
    """
    Supplied dataset structure:

    ai_shortlisting:001-025 -> branded/Kasparro-specific
    ai_shortlisting:026-050 -> unbranded/discovery
    """

    try:
        number = int(prompt_id.rsplit(":", 1)[-1])
    except (ValueError, IndexError):
        return "unknown"

    if 1 <= number <= 25:
        return "branded"

    if 26 <= number <= 50:
        return "discovery"

    return "unknown"


def percentage(
    numerator: int,
    denominator: int,
) -> float:
    if denominator == 0:
        return 0.0

    return round(
        (numerator / denominator) * 100,
        1,
    )


def summarize(rows):
    """
    Failed/skipped analyses are included in coverage,
    but semantic percentages and average scores use
    successful analyses as their denominator.
    """

    total = len(rows)

    successful = [
        row
        for row in rows
        if row["status"] == "success"
    ]

    failed = [
        row
        for row in rows
        if row["status"] == "failed"
    ]

    skipped = [
        row
        for row in rows
        if row["status"] == "skipped"
    ]

    success_count = len(successful)

    mentioned = sum(
        1
        for row in successful
        if row["mentioned"] is True
    )

    recommended = sum(
        1
        for row in successful
        if row["recommended"] is True
    )

    negative = sum(
        1
        for row in successful
        if row["negative"] is True
    )

    scores = [
        row["visibility_score"]
        for row in successful
        if row["visibility_score"] is not None
    ]

    average_score = (
        round(sum(scores) / len(scores), 1)
        if scores
        else None
    )

    return {
        "total": total,
        "successful": success_count,
        "failed": len(failed),
        "skipped": len(skipped),
        "coverage_pct": percentage(
            success_count,
            total,
        ),
        "mentioned": mentioned,
        "mentioned_pct": percentage(
            mentioned,
            success_count,
        ),
        "recommended": recommended,
        "recommended_pct": percentage(
            recommended,
            success_count,
        ),
        "negative": negative,
        "negative_pct": percentage(
            negative,
            success_count,
        ),
        "average_score": average_score,
    }


def print_summary(
    title: str,
    stats: dict,
) -> None:

    print()
    print(title)
    print("-" * len(title))

    print(
        f"Coverage       : "
        f"{stats['successful']}/{stats['total']} "
        f"({stats['coverage_pct']}%)"
    )

    print(
        f"Failed         : "
        f"{stats['failed']}"
    )

    print(
        f"Skipped        : "
        f"{stats['skipped']}"
    )

    print(
        f"Mentioned      : "
        f"{stats['mentioned']}/"
        f"{stats['successful']} "
        f"({stats['mentioned_pct']}%)"
    )

    print(
        f"Recommended    : "
        f"{stats['recommended']}/"
        f"{stats['successful']} "
        f"({stats['recommended_pct']}%)"
    )

    print(
        f"Negative       : "
        f"{stats['negative']}/"
        f"{stats['successful']} "
        f"({stats['negative_pct']}%)"
    )

    print(
        f"Average score  : "
        f"{stats['average_score']}"
    )


def main():
    db = SessionLocal()

    try:
        run = db.scalar(
            select(AnalysisRun)
            .where(
                AnalysisRun.execution_mode == "live"
            )
            .order_by(AnalysisRun.id.desc())
        )

        if run is None:
            raise RuntimeError(
                "No live analysis run found."
            )

        records = db.execute(
            select(
                AnalysisResult,
                Response,
                Prompt,
            )
            .join(
                Response,
                Response.id
                == AnalysisResult.response_db_id,
            )
            .join(
                Prompt,
                Prompt.id
                == Response.prompt_db_id,
            )
            .where(
                AnalysisResult.analysis_run_id
                == run.id
            )
            .order_by(Response.id)
        ).all()

        rows = []

        for result, response, prompt in records:
            rows.append(
                {
                    "response_id": response.response_id,
                    "prompt_id": prompt.prompt_id,
                    "engine": response.engine,
                    "group": prompt_group(
                        prompt.prompt_id
                    ),
                    "status": result.status,
                    "mentioned": result.mentioned,
                    "recommended": result.recommended,
                    "negative": result.negative,
                    "visibility_score": (
                        result.visibility_score
                    ),
                    "competitors": (
                        json.loads(
                            result.competitors_json
                        )
                        if result.competitors_json
                        else []
                    ),
                    "evidence": (
                        json.loads(
                            result.evidence_json
                        )
                        if result.evidence_json
                        else []
                    ),
                }
            )

        print()
        print("Kasparro Live Findings")
        print("======================")
        print(f"Analysis ID : {run.analysis_id}")
        print(f"Model       : {run.model_name}")
        print(
            f"Prompt      : {run.prompt_version}"
        )
        print(
            f"Scoring     : {run.scoring_version}"
        )

        print_summary(
            "OVERALL",
            summarize(rows),
        )

        groups = defaultdict(list)

        for row in rows:
            groups[
                (row["group"], row["engine"])
            ].append(row)

        for group_name in [
            "branded",
            "discovery",
        ]:
            print()
            print("=" * 70)
            print(group_name.upper())
            print("=" * 70)

            group_rows = [
                row
                for row in rows
                if row["group"] == group_name
            ]

            print_summary(
                f"{group_name.upper()} - ALL ENGINES",
                summarize(group_rows),
            )

            for engine in [
                "aimode",
                "chatgpt",
                "gemini",
            ]:
                engine_rows = groups[
                    (group_name, engine)
                ]

                print_summary(
                    (
                        f"{group_name.upper()} - "
                        f"{engine.upper()}"
                    ),
                    summarize(engine_rows),
                )

        print()
        print("=" * 70)
        print("DISCOVERY EVIDENCE")
        print("=" * 70)

        discovery_successes = [
            row
            for row in rows
            if (
                row["group"] == "discovery"
                and row["status"] == "success"
                and (
                    row["mentioned"]
                    or row["recommended"]
                    or row["negative"]
                )
            )
        ]

        if not discovery_successes:
            print(
                "No Kasparro visibility detected "
                "in successful discovery responses."
            )

        for row in discovery_successes:
            print()
            print(
                f"Response : {row['response_id']}"
            )
            print(
                f"Prompt   : {row['prompt_id']}"
            )
            print(
                f"Engine   : {row['engine']}"
            )
            print(
                f"Score    : "
                f"{row['visibility_score']}"
            )
            print(
                f"M/R/N    : "
                f"{row['mentioned']}/"
                f"{row['recommended']}/"
                f"{row['negative']}"
            )

            for evidence in row["evidence"]:
                print(
                    f"  [{evidence['label']}] "
                    f"{evidence['quote']}"
                )

    finally:
        db.close()


if __name__ == "__main__":
    main()