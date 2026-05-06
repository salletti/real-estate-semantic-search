from qdrant_client import AsyncQdrantClient

from app.usecases.gateway.vector_repository_gateway import VectorRepositoryGateway


class QdrantRepository(VectorRepositoryGateway):
    def __init__(self, client: AsyncQdrantClient, collection_name: str) -> None:
        self._client = client
        self._collection_name = collection_name

    async def search(self, vector: list[float], top_k: int) -> list[tuple[int, float]]:
        results = await self._client.search(
            collection_name=self._collection_name,
            query_vector=vector,
            limit=top_k,
        )
        return [(r.payload["property_id"], r.score) for r in results]
