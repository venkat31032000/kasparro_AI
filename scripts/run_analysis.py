from sqlalchemy import select

from app.db import SessionLocal
from app.llm.replay import ReplayAdapter
from app.models import Dataset
from app.analysis.service import run_analysis


def main():
    db = SessionLocal()

    try:
        dataset = db.scalar(
            select(Dataset).order_by(Dataset.id.desc())
        )

        if dataset is None:
            raise RuntimeError(
                "No dataset found. Run the dataset importer first."
            )

        print()
        print("Kasparro analysis")
        print("-----------------")
        print(f"Dataset : {dataset.dataset_id}")
        print("Mode    : replay")
        print()

        adapter = ReplayAdapter()

        result = run_analysis(
            db=db,
            dataset_id=dataset.dataset_id,
            adapter=adapter,
        )

        print()
        print("Analysis complete")
        print("-----------------")
        print(f"Analysis ID     : {result['analysis_id']}")
        print(f"Status          : {result['status']}")
        print(f"Total responses : {result['total_responses']}")
        print(f"Success         : {result['success']}")
        print(f"Failed          : {result['failed']}")
        print(f"Skipped         : {result['skipped']}")
        print(f"Accounted       : {result['accounted']}")
        print(f"Model           : {result['model_name']}")
        print(f"Prompt version  : {result['prompt_version']}")
        print(f"Scoring version : {result['scoring_version']}")

    finally:
        db.close()


if __name__ == "__main__":
    main()