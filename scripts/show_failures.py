from sqlalchemy import select

from app.db import SessionLocal
from app.models import AnalysisResult, AnalysisRun, Response


def main():
    db = SessionLocal()

    try:
        run = db.scalar(
            select(AnalysisRun)
            .where(AnalysisRun.execution_mode == "live")
            .order_by(AnalysisRun.id.desc())
        )

        if run is None:
            raise RuntimeError("No live analysis run found.")

        failures = db.execute(
            select(AnalysisResult, Response)
            .join(
                Response,
                Response.id == AnalysisResult.response_db_id,
            )
            .where(
                AnalysisResult.analysis_run_id == run.id,
                AnalysisResult.status == "failed",
            )
            .order_by(AnalysisResult.id)
        ).all()

        print()
        print("Live Analysis Failures")
        print("======================")
        print(f"Analysis ID : {run.analysis_id}")
        print(f"Failures    : {len(failures)}")
        print()

        if not failures:
            print("No failures.")
            return

        for number, (result, response) in enumerate(
            failures,
            start=1,
        ):
            print(f"[{number}/{len(failures)}]")
            print(f"Response ID : {response.response_id}")
            print(f"Engine      : {response.engine}")
            print(f"Prompt ID   : {response.prompt_id}")
            print(f"Attempts    : {result.attempts}")
            print(f"Error code  : {result.failure_code}")
            print(f"Error       : {result.failure_message}")
            print("-" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    main()