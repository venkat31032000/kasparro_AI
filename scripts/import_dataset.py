from pathlib import Path

from app.db import SessionLocal
from app.ingestion.importer import import_dataset


def main():
    data_dir = Path("data")

    db = SessionLocal()

    try:
        result = import_dataset(
            db=db,
            data_dir=data_dir,
        )

        print("\nDataset import complete")
        print("-----------------------")
        print(f"Dataset ID : {result['dataset_id']}")
        print(f"Prompts    : {result['prompts']}")
        print(f"Responses  : {result['responses']}")
        print(f"Citations  : {result['citations']}")
        print(f"Errors     : {len(result['errors'])}")

        if result["errors"]:
            print("\nErrors:")
            for error in result["errors"]:
                print(error)

    finally:
        db.close()


if __name__ == "__main__":
    main()