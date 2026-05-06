from app.core.config import settings
from app.core.constants import SEMANTIC_SEARCH_QUERY_PREFIX
from app.usecases.gateway.embedding_gateway import EmbeddingGateway
from app.usecases.gateway.property_repository_gateway import PropertyRepositoryGateway
from app.usecases.gateway.vector_repository_gateway import VectorRepositoryGateway
from app.entities.nlp.intent_parser import parse_intent, parse_intent_using_llm
from app.entities.nlp.intent_schema import PropertyIntent
from app.entities.search.pagination import paginate_results
from app.entities.search.query_resolver import resolve_query
from app.entities.search.query_types import QueryStrategy


class SearchProperty:
    def __init__(
        self,
        property_repository: PropertyRepositoryGateway,
        vector_repository: VectorRepositoryGateway,
        embedding_service: EmbeddingGateway,
    ) -> None:
        self._property_repo = property_repository
        self._vector_repo = vector_repository
        self._embedding_service = embedding_service

    async def execute(
        self,
        query: str,
        page: int = 1,
        page_size: int = 10,
    ) -> dict:
        intent = parse_intent_using_llm(query) if settings.use_llm else parse_intent(query)
        resolution = resolve_query(intent)
        strategy = resolution.strategy
        handlers = {
            QueryStrategy.sql_only: self._sql_search,
            QueryStrategy.semantic_only: self._semantic_search,
            QueryStrategy.hybrid: self._hybrid_search,
            QueryStrategy.nearby: self._nearby_search,
        }
        handler = handlers[strategy]
        results, total = await handler(intent, page, page_size)

        total_pages = max(1, -(-total // page_size))

        return {
            "query": query,
            "resolution": resolution,
            "intent": intent,
            "results": results,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def _nearby_search(
        self, intent: PropertyIntent, page: int, page_size: int
    ) -> tuple[list, int]:
        filters = intent.model_dump(exclude_none=True)
        filters["page"] = page
        filters["per_page"] = page_size
        total = await self._property_repo.count_nearby(filters)
        props = await self._property_repo.search_nearby(filters)
        results = [{"property": p, "score": None} for p in props]
        return results, total

    async def _sql_search(
        self, intent: PropertyIntent, page: int, page_size: int
    ) -> tuple[list, int]:
        filters = intent.model_dump(exclude_none=True)
        total = await self._property_repo.count(filters)
        filters["page"] = page
        filters["per_page"] = page_size
        props = await self._property_repo.search(filters)
        results = [{"property": p, "score": None} for p in props]
        return results, total

    async def _semantic_search(
        self, intent: PropertyIntent, page: int, page_size: int
    ) -> tuple[list, int]:
        query_text = f"{SEMANTIC_SEARCH_QUERY_PREFIX} {' '.join(intent.semantic_terms)}"
        top_k = page * page_size
        vector = await self._embedding_service.embed(query_text)
        scored_ids = await self._vector_repo.search(vector, top_k)

        if not scored_ids:
            return [], 0

        prop_ids = [pid for pid, _ in scored_ids]
        id_to_score = {pid: score for pid, score in scored_ids}

        props = await self._property_repo.get_by_ids(prop_ids)
        props_by_id = {p.id: p for p in props}

        all_scored = [
            {"property": props_by_id[pid], "score": id_to_score[pid]}
            for pid in prop_ids
            if pid in props_by_id
        ]
        page_slice, _ = paginate_results(all_scored, page, page_size)
        return page_slice, len(all_scored)

    async def _hybrid_search(
        self, intent: PropertyIntent, page: int, page_size: int
    ) -> tuple[list, int]:
        filters = intent.model_dump(exclude_none=True)
        filters["per_page"] = settings.search.hybrid_default_top_k
        sql_props = await self._property_repo.search(filters)

        if not sql_props:
            return [], 0

        query_text = f"{SEMANTIC_SEARCH_QUERY_PREFIX} {' '.join(intent.semantic_terms)}"
        top_k = len(sql_props) + page_size
        vector = await self._embedding_service.embed(query_text)
        scored_ids = await self._vector_repo.search(vector, top_k)
        id_to_score = {pid: score for pid, score in scored_ids}

        all_scored = sorted(
            [{"property": p, "score": id_to_score.get(p.id, 0.0)} for p in sql_props],
            key=lambda x: x["score"],
            reverse=True,
        )
        page_slice, _ = paginate_results(all_scored, page, page_size)
        return page_slice, len(all_scored)
