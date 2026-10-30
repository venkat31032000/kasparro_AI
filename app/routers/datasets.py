from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.ingestion.importer import import_dataset


router = APIRouter(
    prefix="/datasets",
    tags=["datasets"],
)


# ---------------------------------------------------------
# Request schema
# ---------------------------------------------------------

class CreateDatasetRequest(BaseModel):
    """
    Import an archived dataset from a local directory.

    The directory must contain:

    - run.json
    - prompts.jsonl
    - responses.jsonl
    - citations.jsonl
    """

    data_dir: str = Field(
        min_length=1,
        examples=["data"],
    )


# ---------------------------------------------------------
# POST /datasets
# ---------------------------------------------------------

@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
def create_dataset(
    request: CreateDatasetRequest,
    db: Session = Depends(get_db),
):
    """
    Import a dataset into SQLite.

    Re-importing the same source run is idempotent:
    existing prompts, responses, and citations are reused
    rather than duplicated.
    """

    data_dir = Path(request.data_dir)

    # -----------------------------------------------------
    # Directory validation
    # -----------------------------------------------------

    if not data_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Dataset directory does not exist: "
                f"{data_dir}"
            ),
        )

    if not data_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Dataset path is not a directory: "
                f"{data_dir}"
            ),
        )

    # -----------------------------------------------------
    # Required files
    # -----------------------------------------------------

    required_files = [
        "run.json",
        "prompts.jsonl",
        "responses.jsonl",
        "citations.jsonl",
    ]

    missing_files = [
        filename
        for filename in required_files
        if not (data_dir / filename).is_file()
    ]

    if missing_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": (
                    "Dataset directory is missing "
                    "required files."
                ),
                "missing_files": missing_files,
            },
        )

    # -----------------------------------------------------
    # Import
    # -----------------------------------------------------

    try:
        result = import_dataset(
            db=db,
            data_dir=data_dir,
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset file not found: {exc}",
        ) from exc

    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Cannot read dataset files: {exc}",
        ) from exc

    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid dataset metadata: {exc}",
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Dataset import failed: "
                f"{exc}"
            ),
        ) from exc

    # -----------------------------------------------------
    # Response
    # -----------------------------------------------------

    return {
        "dataset_id": result["dataset_id"],
        "status": (
            "imported_with_errors"
            if result["errors"]
            else "imported"
        ),
        "counts": {
            "prompts": result["prompts"],
            "responses": result["responses"],
            "citations": result["citations"],
        },
        "error_count": len(result["errors"]),
        "errors": result["errors"],
    }