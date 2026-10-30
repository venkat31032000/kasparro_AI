from app.schemas import ModelAnalysisOutput


SCORING_VERSION = "visibility-v1"


def calculate_visibility_score(
    result: ModelAnalysisOutput,
    *,
    has_kasparro_citation: bool,
) -> int:
    """
    Transparent visibility score from 0 to 100.

    Components:
      Mention                  +30
      Recommendation           +40
      Recommendation position +0 to +20
      Kasparro citation        +10
      Negative characterisation -30

    The final score is clamped to [0, 100].
    """

    score = 0

    if result.mentioned:
        score += 30

    if result.recommended:
        score += 40

    if result.recommendation_position == 1:
        score += 20

    elif result.recommendation_position == 2:
        score += 15

    elif result.recommendation_position == 3:
        score += 10

    if has_kasparro_citation:
        score += 10

    if result.negative:
        score -= 30

    return max(0, min(100, score))