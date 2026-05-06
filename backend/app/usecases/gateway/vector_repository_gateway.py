from abc import ABC, abstractmethod


class VectorRepositoryGateway(ABC):
    @abstractmethod
    async def search(self, vector: list[float], top_k: int) -> list[tuple[int, float]]: ...
