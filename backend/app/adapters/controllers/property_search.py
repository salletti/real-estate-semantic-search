"""
API — Property Search V4
=========================

PIPELINE V4 (ce fichier)
-------------------------
    Client HTTP
        ↓ GET /properties/search?q="Maison à Paris sous 500k"&page=2&per_page=5
    SearchPropertyUsecase.execute(q)   ← parse intent + dispatch strategy
        ↓ sql_only | semantic_only | hybrid | nearby
    _fetch_descriptions(session, ids)  ← infrastructure : reste dans le controller
        ↓
    _build_response(...)               ← sérialisation en PropertySearchResponse
        ↓ JSON
"""

import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.gateways.db.repositories.property_repository import PropertyRepository
from app.adapters.gateways.embedding.embedding_adapter import EmbeddingAdapter
from app.adapters.gateways.vector_db.qdrant_repository import QdrantRepository
from app.core.config import settings
from app.adapters.gateways.db.models.description import Description
from app.adapters.gateways.db.session import get_db
from app.adapters.gateways.vector_db.qdrant_store import get_async_client
from app.entities.nlp.intent_schema import PropertyIntent
from app.entities.search.query_types import QueryResolution
from app.adapters.controllers.schemas.property_search import PropertySearchResponse, PropertySearchResult
from app.usecases.search_property.search_property_usecase import SearchProperty

router = APIRouter(prefix="/properties", tags=["properties"])


async def _fetch_descriptions(
    session: AsyncSession,
    property_ids: list[int],
) -> dict[int, str]:
    """Charge les descriptions françaises pour une liste de property_ids en une seule requête."""
    if not property_ids:
        return {}
    stmt = select(Description).where(
        Description.property_id.in_(property_ids),
        Description.locale == "fr",
    )
    result = await session.execute(stmt)
    return {d.property_id: d.description for d in result.scalars()}


def _build_response(
    q: str,
    intent: PropertyIntent,
    resolution: QueryResolution,
    prop_results: list[dict],
    total: int,
    page: int,
    per_page: int,
    descriptions: dict[int, str],
) -> PropertySearchResponse:
    """Convertit les résultats bruts en PropertySearchResponse sérialisable."""
    results = [
        PropertySearchResult.model_validate(r["property"]).model_copy(update={
            "score": r["score"],
            "description_fr": descriptions.get(r["property"].id),
        })
        for r in prop_results
    ]
    total_pages = math.ceil(total / per_page) if total > 0 else 1
    expanded_cities: list[str] = []
    if intent.nearby_city:
        expanded_cities = sorted({
            r["property"].city for r in prop_results if r["property"].city
        })
    return PropertySearchResponse(
        query=q,
        parsed_intent=intent,
        query_resolution=resolution,
        count=len(results),
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        results=results,
        nearby_city=intent.nearby_city,
        search_radius_km=intent.search_radius_km,
        expanded_cities=expanded_cities,
    )


@router.get("/search", response_model=PropertySearchResponse)
async def search(
    q: str = Query(
        ...,
        min_length=1,
        description="Requête en langage naturel. Ex : Maison à Paris sous 500k",
    ),
    page: int = Query(1, ge=1, description="Numéro de page (1-indexé)"),
    per_page: int = Query(10, ge=1, le=100, description="Résultats par page"),
    session: AsyncSession = Depends(get_db),
) -> PropertySearchResponse:
    """Recherche de biens immobiliers par requête en langage naturel.

    Pipeline V4 : tous les chemins passent par SearchPropertyUsecase.
    """
    q = q.strip()

    property_repo = PropertyRepository(session)
    vector_repo = QdrantRepository(get_async_client(), settings.vector_store.collection_name)
    embedding_service = EmbeddingAdapter()
    usecase = SearchProperty(
        property_repo,
        vector_repo,
        embedding_service,
    )

    result = await usecase.execute(q, page=page, page_size=per_page)

    descriptions = await _fetch_descriptions(
        session, [r["property"].id for r in result["results"]]
    )
    return _build_response(
        q, result["intent"], result["resolution"],
        result["results"], result["total"],
        page, per_page, descriptions,
    )
