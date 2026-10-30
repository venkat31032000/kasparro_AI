from app.analysis.service import run_analysis
from app.db import SessionLocal
from app.llm.live import OpenAIAdapter
from app.models import Dataset


def main():
    db = SessionLocal()

    try:
        # Get the most recently imported dataset.
        dataset = (
            db.query(Dataset)
            .order_by(Dataset.id.desc())
            .first()
        )

        if dataset is None:
            raise RuntimeError(
                "No dataset found. Import the dataset first."
            )

        # Create the live OpenAI semantic-analysis adapter.
        adapter = OpenAIAdapter()

        print()
        print("Kasparro Live Semantic Analysis")
        print("===============================")
        print(f"Dataset : {dataset.dataset_id}")
        print(f"Model   : {adapter.model_name}")
        print()

        # IMPORTANT:
        # run_analysis expects the public dataset identifier
        # such as:
        # dataset:4a4b71d9-...
        #
        # It does NOT expect the SQLite primary key (dataset.id).
        summary = run_analysis(
            db=db,
            dataset_id=dataset.dataset_id,
            adapter=adapter,
        )

        print()
        print("Live Analysis Complete")
        print("======================")
        print(f"Analysis ID     : {summary['analysis_id']}")
        print(f"Status          : {summary['status']}")
        print(f"Total responses : {summary['total_responses']}")
        print(f"Success         : {summary['success']}")
        print(f"Failed          : {summary['failed']}")
        print(f"Skipped         : {summary['skipped']}")
        print(f"Accounted       : {summary['accounted']}")
        print(f"Model           : {summary['model_name']}")
        print(f"Prompt version  : {summary['prompt_version']}")
        print(f"Scoring version : {summary['scoring_version']}")

    finally:
        db.close()


if __name__ == "__main__":
    main()