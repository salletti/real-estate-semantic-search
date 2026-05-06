from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.gateways.db.models.agent import Agent
from app.adapters.gateways.db.models.property_listing import PropertyListing
from app.entities.property import Property
from app.entities.nlp.intent_schema import PropertyIntent
from app.entities.geography.proximity import compute_bounding_box, filter_by_distance
from app.adapters.gateways.db.repositories.geospatial_repository import get_city_center
from app.usecases.gateway.property_repository_gateway import PropertyRepositoryGateway


class PropertyRepository(PropertyRepositoryGateway):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _build_query(self, intent: PropertyIntent):
        stmt = select(Property)

        if intent.city is not None:
            stmt = stmt.where(Property.city == intent.city)
        if intent.property_type is not None:
            stmt = stmt.where(Property.type == intent.property_type.value)
        if intent.transaction_type is not None:
            stmt = stmt.where(Property.transaction_type == intent.transaction_type.value)
        if intent.max_price is not None:
            stmt = stmt.where(Property.mandate_price <= intent.max_price)
        if intent.min_rooms is not None:
            stmt = stmt.where(Property.rooms_count >= intent.min_rooms)

        if intent.published_more_than_days is not None:
            cutoff = datetime.now(tz=timezone.utc) - timedelta(days=intent.published_more_than_days)
            stmt = stmt.join(Property.listings).where(PropertyListing.last_publish_date <= cutoff).distinct()
        if intent.published_less_than_days is not None:
            cutoff = datetime.now(tz=timezone.utc) - timedelta(days=intent.published_less_than_days)
            stmt = stmt.join(Property.listings).where(PropertyListing.last_publish_date >= cutoff).distinct()

        if intent.agent_name is not None:
            full_name = func.concat(Agent.first_name, " ", Agent.last_name)
            stmt = stmt.join(Property.advisor).where(full_name.ilike(f"%{intent.agent_name}%"))

        return stmt.order_by(Property.created_at.desc())

    async def search(self, filters: dict) -> List[Property]:
        page = int(filters.get("page", 1))
        per_page = int(filters.get("per_page", 10))
        known = PropertyIntent.model_fields.keys()
        intent_data = {k: v for k, v in filters.items() if k in known and v is not None}
        intent = PropertyIntent(**intent_data)

        stmt = self._build_query(intent).limit(per_page).offset((page - 1) * per_page)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_all(self) -> List[Property]:
        stmt = select(Property).order_by(Property.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_ids(self, ids: list[int]) -> List[Property]:
        if not ids:
            return []
        stmt = select(Property).where(Property.id.in_(ids))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, filters: dict) -> int:
        known = PropertyIntent.model_fields.keys()
        intent_data = {k: v for k, v in filters.items() if k in known and v is not None}
        intent = PropertyIntent(**intent_data)

        base = self._build_query(intent).subquery()
        stmt = select(func.count()).select_from(base)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    def _build_bbox_query(self, intent: PropertyIntent, bbox: tuple):
        lat_min, lat_max, lon_min, lon_max = bbox
        # Le carré géographique est le pré-filtre SQL : rapide mais imprécis.
        # Il inclut les coins du carré (distance ≈ radius × √2) que le filtre
        # Haversine éliminera ensuite. Pas de faux négatifs : le carré contient
        # toujours le cercle.
        stmt = (
            select(Property)
            .where(Property.latitude.between(lat_min, lat_max))
            .where(Property.longitude.between(lon_min, lon_max))
        )
        # Pas de filtre city : la recherche de proximité traverse les frontières
        # communales. "15 km autour de Rambouillet" doit retourner des biens à
        # Montfort-l'Amaury ou Épernon, pas seulement ceux taggués "Rambouillet".
        if intent.property_type is not None:
            stmt = stmt.where(Property.type == intent.property_type.value)
        if intent.transaction_type is not None:
            stmt = stmt.where(Property.transaction_type == intent.transaction_type.value)
        if intent.max_price is not None:
            stmt = stmt.where(Property.mandate_price <= intent.max_price)
        if intent.min_rooms is not None:
            stmt = stmt.where(Property.rooms_count >= intent.min_rooms)
        return stmt.order_by(Property.created_at.desc())

    async def _nearby_candidates(self, filters: dict):
        """Retourne tous les biens dans le rayon, sans pagination.

        Appelée par search_nearby ET count_nearby — la pagination et le comptage
        opèrent sur la même liste filtrée pour garantir la cohérence.

        Retourne None si la ville cible est introuvable en base (aucun bien
        avec coordonnées GPS pour cette ville → on ne peut pas calculer de centre).
        """
        nearby_city = filters["nearby_city"]
        radius_km = float(filters["search_radius_km"])
        known = PropertyIntent.model_fields.keys()
        intent_data = {k: v for k, v in filters.items() if k in known and v is not None}
        intent = PropertyIntent(**intent_data)

        # Étape 1 — Centre GPS approximatif de la ville (moyenne des biens en base).
        # None = aucun bien avec coordonnées pour cette ville → résultat vide.
        center = await get_city_center(self._session, nearby_city)
        if center is None:
            return None
        lat, lon = center

        # Étape 2 — Pré-filtre SQL : bounding box (carré), peu de candidats chargés.
        bbox = compute_bounding_box(lat, lon, radius_km)
        result = await self._session.execute(self._build_bbox_query(intent, bbox))
        candidates = list(result.scalars().all())

        # Étape 3 — Filtre précis : Haversine Python élimine les coins du carré.
        return filter_by_distance(candidates, lat, lon, radius_km)

    async def search_nearby(self, filters: dict) -> List[Property]:
        page = int(filters.get("page", 1))
        per_page = int(filters.get("per_page", 10))
        filtered = await self._nearby_candidates(filters)
        if filtered is None:
            return []
        # Pagination en Python (pas en SQL) : Haversine doit être appliqué sur
        # tous les candidats avant de pouvoir découper la page.
        start = (page - 1) * per_page
        return filtered[start:start + per_page]

    async def count_nearby(self, filters: dict) -> int:
        filtered = await self._nearby_candidates(filters)
        return 0 if filtered is None else len(filtered)
