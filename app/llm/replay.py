import re

from app.llm.base import ModelAdapter
from app.schemas import EvidenceItem, ModelAnalysisOutput


class ReplayAdapter(ModelAdapter):
    """
    Deterministic keyless adapter.

    This exists so the full application can be run without
    external model access.

    IMPORTANT:
    Replay mode demonstrates application mechanics, not
    live-model quality.
    """

    @property
    def execution_mode(self) -> str:
        return "replay"

    @property
    def model_name(self) -> str:
        return "deterministic-replay-v1"

    def classify(
        self,
        *,
        prompt_text: str,
        answer_text: str,
    ) -> ModelAnalysisOutput:

        del prompt_text  # reserved for parity with live adapter

        text_lower = answer_text.lower()

        mentioned = "kasparro" in text_lower

        evidence: list[EvidenceItem] = []

        if mentioned:
            quote = self._find_sentence_containing(
                answer_text,
                "kasparro",
            )

            if quote:
                evidence.append(
                    EvidenceItem(
                        label="mentioned",
                        quote=quote,
                    )
                )

        recommended = False
        negative = False
        recommendation_position = None

        if mentioned:
            kasparro_sentences = self._sentences_with_kasparro(
                answer_text
            )

            for sentence in kasparro_sentences:
                sentence_lower = sentence.lower()

                recommendation_terms = (
                    "recommend kasparro",
                    "kasparro is recommended",
                    "consider kasparro",
                    "choose kasparro",
                    "kasparro is a good option",
                    "kasparro is a strong option",
                    "kasparro is one of",
                )

                if any(
                    term in sentence_lower
                    for term in recommendation_terms
                ):
                    recommended = True

                    evidence.append(
                        EvidenceItem(
                            label="recommended",
                            quote=sentence,
                        )
                    )

                    break

            negative_terms = (
                "not recommend kasparro",
                "do not recommend kasparro",
                "avoid kasparro",
                "kasparro lacks",
                "kasparro is weak",
                "kasparro is limited",
                "kasparro is not",
                "kasparro does not",
            )

            for sentence in kasparro_sentences:
                sentence_lower = sentence.lower()

                if any(
                    term in sentence_lower
                    for term in negative_terms
                ):
                    negative = True

                    evidence.append(
                        EvidenceItem(
                            label="negative",
                            quote=sentence,
                        )
                    )

                    break

        competitors = self._extract_known_competitors(answer_text)

        confidence = 1.0

        return ModelAnalysisOutput(
            mentioned=mentioned,
            recommended=recommended,
            negative=negative,
            recommendation_position=recommendation_position,
            competitors=competitors,
            evidence=evidence,
            confidence=confidence,
        )

    @staticmethod
    def _sentences_with_kasparro(text: str) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", text)

        return [
            sentence.strip()
            for sentence in sentences
            if "kasparro" in sentence.lower()
        ]

    @staticmethod
    def _find_sentence_containing(
        text: str,
        term: str,
    ) -> str | None:

        sentences = re.split(r"(?<=[.!?])\s+", text)

        for sentence in sentences:
            if term.lower() in sentence.lower():
                return sentence.strip()

        return None

    @staticmethod
    def _extract_known_competitors(text: str) -> list[str]:
        known_competitors = [
            "Profound",
            "Otterly",
            "Peec AI",
            "Scrunch AI",
            "AthenaHQ",
        ]

        text_lower = text.lower()

        return [
            competitor
            for competitor in known_competitors
            if competitor.lower() in text_lower
        ]