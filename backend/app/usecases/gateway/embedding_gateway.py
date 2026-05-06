from abc import ABC, abstractmethod


class EmbeddingGateway(ABC):
    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...
