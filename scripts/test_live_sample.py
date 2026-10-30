from sqlalchemy import select

from app.db import SessionLocal
from app.llm.live import OpenAIAdapter
from app.models import Response


SAMPLE_SIZE = 5


def main():
    db = SessionLocal()

    try:
        responses = db.scalars(
            select(Response)
            .order_by(Response.id)
            .limit(SAMPLE_SIZE)
        ).all()

        if not responses:
            raise RuntimeError(
                "No responses found. Import the dataset first."
            )

        adapter = OpenAIAdapter()

        print()
        print("Live OpenAI sample test")
        print("=======================")

        for index, response in enumerate(responses, start=1):
            print()
            print(
                f"[{index}/{len(responses)}] "
                f"{response.response_id}"
            )
            print(f"Engine: {response.engine}")

            result = adapter.classify(
                prompt_text=response.prompt.text,
                answer_text=response.answer_text,
            )

            print(
                f"Mentioned   : {result.mentioned}"
            )
            print(
                f"Recommended : {result.recommended}"
            )
            print(
                f"Negative    : {result.negative}"
            )
            print(
                f"Position    : "
                f"{result.recommendation_position}"
            )
            print(
                f"Competitors : {result.competitors}"
            )
            print(
                f"Confidence  : {result.confidence}"
            )

            print("Evidence:")

            if not result.evidence:
                print("  none")

            for evidence in result.evidence:
                print(
                    f"  [{evidence.label}] "
                    f"{evidence.quote}"
                )

    finally:
        db.close()


if __name__ == "__main__":
    main()