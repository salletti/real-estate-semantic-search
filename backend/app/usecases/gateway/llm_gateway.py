from abc import ABC, abstractmethod

from app.entities.nlp.llm_intent_schema import LlmIntentResponse


class LlmGateway(ABC):
    @abstractmethod
    def parse_intent(self, query: str) -> LlmIntentResponse | None: ...
