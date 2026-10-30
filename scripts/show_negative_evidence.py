import json

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    AnalysisResult,
    AnalysisRun,
    Prompt,
    Response,
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

        rows = db.execute(
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
                AnalysisResult.analysis_run_id == run.id,
                AnalysisResult.status == "success",
                AnalysisResult.negative.is_(True),
            )
            .order_by(
                Response.engine,
                Response.prompt_id,
            )
        ).all()

        print()
        print("Kasparro Negative Evidence")
        print("==========================")
        print(f"Analysis ID : {run.analysis_id}")
        print(f"Cases       : {len(rows)}")

        for number, (
            result,
            response,
            prompt,
        ) in enumerate(rows, start=1):

            evidence = (
                json.loads(result.evidence_json)
                if result.evidence_json
                else []
            )

            negative_evidence = [
                item
                for item in evidence
                if item.get("label") == "negative"
            ]

            print()
            print("=" * 70)
            print(f"[{number}/{len(rows)}]")
            print(
                f"Response ID : {response.response_id}"
            )
            print(
                f"Prompt ID   : {prompt.prompt_id}"
            )
            print(
                f"Engine      : {response.engine}"
            )
            print(
                f"Score       : {result.visibility_score}"
            )
            print(
                f"Recommended : {result.recommended}"
            )
            print("Evidence:")

            if not negative_evidence:
                print(
                    "  No negative evidence stored."
                )
                continue

            for item in negative_evidence:
                print(
                    f"  - {item['quote']}"
                )

    finally:
        db.close()


if __name__ == "__main__":
    main()