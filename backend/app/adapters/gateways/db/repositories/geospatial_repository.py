"""
Geospatial Repository — Infrastructure
========================================

Requêtes SQL pour la recherche géospatiale.
Dépend de SQLAlchemy et des modèles ORM.

LIMITATIONS V1 (documentées et attendues)
------------------------------------------
- La recherche de proximité ne fonctionne que si les biens ont latitude/longitude
  renseignées. Un bien sans coordonnées GPS est ignoré même s'il est proche.
- Le centre de la ville cible est approximatif : c'est la moyenne des coordonnées
  des biens de cette ville, pas le centroïde communal réel.
- Ville sans biens en base → centre introuvable → résultat vide.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.gateways.db.models.property import Property


async def get_city_center(
    session: AsyncSession,
    city: str,
) -> tuple[float, float] | None:
    """Calcule le centre GPS approximatif d'une ville depuis les biens existants.

    Filtre UNIQUEMENT par city — ignore tous les autres filtres (prix, type, etc.)
    pour que le centre soit géographiquement correct indépendamment du contexte.

    Args:
        session: Session async PostgreSQL.
        city: Nom de la ville cible (ex: "Rambouillet", "Le Havre").

    Returns:
        (latitude_moyenne, longitude_moyenne) ou None si aucun bien avec
        coordonnées GPS pour cette ville.
    """
    stmt = (
        select(Property.latitude, Property.longitude)
        .where(
            func.lower(Property.city) == city.lower(),
            Property.latitude.is_not(None),
            Property.longitude.is_not(None),
        )
    )
    result = await session.execute(stmt)
    coords = result.all()

    if not coords:
        return None

    avg_lat = sum(lat for lat, _ in coords) / len(coords)
    avg_lon = sum(lon for _, lon in coords) / len(coords)
    return (avg_lat, avg_lon)
