from abc import ABC, abstractmethod

from app.schemas import ModelAnalysisOutput


class ModelError(Exception):
    """Base error for model execution."""


class RetryableModelError(ModelError):
    """A temporary model failure that may succeed on retry."""


class InvalidModelOutputError(ModelError):
    """The provider returned unusable or invalid output."""


class ModelAdapter(ABC):

    @property
    @abstractmethod
    def execution_mode(self) -> str:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @abstractmethod
    def classify(
        self,
        *,
        prompt_text: str,
        answer_text: str,
    ) -> ModelAnalysisOutput:
        pass