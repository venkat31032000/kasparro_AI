from sqlalchemy import select

from app.db import SessionLocal
from app.llm.live import OpenAIAdapter
from app.models import Response


RESPONSE_ID = "6b6e79d3-a582-4d23-8fa6-714c9e982af2"


def main():
    db = SessionLocal()

    try:
        response = db.scalar(
            select(Response)
            .where(Response.response_id == RESPONSE_ID)
        )

        if response is None:
            raise RuntimeError(
                f"Response not found: {RESPONSE_ID}"
            )

        adapter = OpenAIAdapter()

        print()
        print("Archived Response")
        print("=================")
        print(response.answer_text)

        print()
        print("OpenAI Classification")
        print("=====================")

        result = adapter.classify(
            prompt_text=response.prompt.text,
            answer_text=response.answer_text,
        )

        print(result.model_dump_json(indent=2))

        print()
        print("Evidence Verification")
        print("=====================")

        for evidence in result.evidence:
            exact_match = evidence.quote in response.answer_text

            print()
            print(f"Label       : {evidence.label}")
            print(f"Exact match : {exact_match}")
            print(f"Quote       : {repr(evidence.quote)}")

    finally:
        db.close()


if __name__ == "__main__":
    main()