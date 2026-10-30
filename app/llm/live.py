import json

from openai import (
    APIConnectionError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from app.config import settings
from app.llm.base import (
    InvalidModelOutputError,
    ModelAdapter,
    RetryableModelError,
)
from app.llm.prompt import SYSTEM_PROMPT, build_user_prompt
from app.schemas import ModelAnalysisOutput


class OpenAIAdapter(ModelAdapter):
    """
    Live semantic classifier using the OpenAI Responses API.

    The model performs semantic interpretation only.
    Evidence validation and visibility scoring remain
    deterministic application responsibilities.
    """

    def __init__(self):
        if not settings.llm_api_key:
            raise RuntimeError(
                "LLM_API_KEY is not configured."
            )

        self.client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )

    @property
    def execution_mode(self) -> str:
        return "live"

    @property
    def model_name(self) -> str:
        return settings.llm_model

    def classify(
        self,
        *,
        prompt_text: str,
        answer_text: str,
    ) -> ModelAnalysisOutput:

        user_prompt = build_user_prompt(
            prompt_text=prompt_text,
            answer_text=answer_text,
        )

        try:
            response = self.client.responses.create(
                model=self.model_name,
                instructions=SYSTEM_PROMPT,
                input=user_prompt,
                max_output_tokens=settings.llm_max_output_tokens,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "kasparro_visibility_classification",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "mentioned": {
                                    "type": "boolean"
                                },
                                "recommended": {
                                    "type": "boolean"
                                },
                                "negative": {
                                    "type": "boolean"
                                },
                                "recommendation_position": {
                                    "type": [
                                        "integer",
                                        "null",
                                    ]
                                },
                                "competitors": {
                                    "type": "array",
                                    "items": {
                                        "type": "string"
                                    },
                                },
                                "evidence": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "label": {
                                                "type": "string",
                                                "enum": [
                                                    "mentioned",
                                                    "recommended",
                                                    "negative",
                                                ],
                                            },
                                            "quote": {
                                                "type": "string"
                                            },
                                        },
                                        "required": [
                                            "label",
                                            "quote",
                                        ],
                                        "additionalProperties": False,
                                    },
                                },
                                "confidence": {
                                    "type": "number",
                                    "minimum": 0,
                                    "maximum": 1,
                                },
                            },
                            "required": [
                                "mentioned",
                                "recommended",
                                "negative",
                                "recommendation_position",
                                "competitors",
                                "evidence",
                                "confidence",
                            ],
                            "additionalProperties": False,
                        },
                    }
                },
            )

        except (APITimeoutError, APIConnectionError, RateLimitError) as exc:
            raise RetryableModelError(
                f"Temporary OpenAI API failure: {exc}"
            ) from exc

        except Exception as exc:
            raise InvalidModelOutputError(
                f"OpenAI request failed: {exc}"
            ) from exc

        raw_output = response.output_text

        if not raw_output or not raw_output.strip():
            raise InvalidModelOutputError(
                "OpenAI returned an empty response."
            )

        try:
            parsed = json.loads(raw_output)

        except json.JSONDecodeError as exc:
            raise InvalidModelOutputError(
                "OpenAI returned invalid JSON."
            ) from exc

        try:
            return ModelAnalysisOutput.model_validate(parsed)

        except Exception as exc:
            raise InvalidModelOutputError(
                f"OpenAI output failed schema validation: {exc}"
            ) from exc