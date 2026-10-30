from collections import defaultdict

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AnalysisResult, AnalysisRun, Response


def percentage(part: int, total: int) -> float:
    if total == 0:
        return 0.0

    return round((part / total) * 100, 1)


def main():
    db = SessionLocal()

    try:
        analysis_run = db.scalar(
            select(AnalysisRun)
            .where(AnalysisRun.status == "completed")
            .order_by(AnalysisRun.id.desc())
        )

        if analysis_run is None:
            raise RuntimeError(
                "No completed analysis run found."
            )

        rows = db.execute(
            select(
                Response.engine,
                Response.prompt_id,
                AnalysisResult.mentioned,
                AnalysisResult.recommended,
                AnalysisResult.negative,
                AnalysisResult.visibility_score,
            )
            .join(
                AnalysisResult,
                AnalysisResult.response_db_id == Response.id,
            )
            .where(
                AnalysisResult.analysis_run_id == analysis_run.id,
                AnalysisResult.status == "success",
            )
        ).all()

        stats = defaultdict(
            lambda: {
                "total": 0,
                "mentioned": 0,
                "recommended": 0,
                "negative": 0,
                "score_sum": 0,
            }
        )

        for row in rows:
            engine = row.engine

            stats[engine]["total"] += 1

            if row.mentioned:
                stats[engine]["mentioned"] += 1

            if row.recommended:
                stats[engine]["recommended"] += 1

            if row.negative:
                stats[engine]["negative"] += 1

            stats[engine]["score_sum"] += (
                row.visibility_score or 0
            )

        print()
        print("Kasparro Visibility Summary")
        print("===========================")
        print(f"Analysis: {analysis_run.analysis_id}")
        print()

        for engine in sorted(stats):
            values = stats[engine]
            total = values["total"]

            average_score = (
                round(values["score_sum"] / total, 1)
                if total
                else 0.0
            )

            print(engine.upper())
            print("-" * 40)

            print(
                f"Responses      : {total}"
            )

            print(
                f"Mentioned      : "
                f"{values['mentioned']}/{total} "
                f"({percentage(values['mentioned'], total)}%)"
            )

            print(
                f"Recommended    : "
                f"{values['recommended']}/{total} "
                f"({percentage(values['recommended'], total)}%)"
            )

            print(
                f"Negative       : "
                f"{values['negative']}/{total} "
                f"({percentage(values['negative'], total)}%)"
            )

            print(
                f"Average score  : {average_score}/100"
            )

            print()

        print("Coverage")
        print("--------")
        print(f"Successful responses: {len(rows)}/150")

    finally:
        db.close()


if __name__ == "__main__":
    main()