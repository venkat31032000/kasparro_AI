from app.llm.base import InvalidModelOutputError
from app.schemas import ModelAnalysisOutput


def validate_model_evidence(
    result: ModelAnalysisOutput,
    answer_text: str,
) -> None:
    """
    Every evidence quote must occur in the archived response.

    This prevents generated evidence from being accepted as
    supporting evidence.
    """

    for evidence in result.evidence:
        if evidence.quote not in answer_text:
            raise InvalidModelOutputError(
                "Model returned evidence that does not occur "
                "in the archived response."
            )


def validate_label_consistency(
    result: ModelAnalysisOutput,
) -> None:
    """
    Enforce basic semantic invariants.
    """

    if result.recommended and not result.mentioned:
        raise InvalidModelOutputError(
            "Kasparro cannot be recommended without being mentioned."
        )

    if (
        result.recommendation_position is not None
        and not result.recommended
    ):
        raise InvalidModelOutputError(
            "Recommendation position requires recommended=true."
        )