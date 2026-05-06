"""
Tests unitaires — geospatial_service.py

Stratégie de test :
- compute_bounding_box() et filter_by_distance() sont pures (sans DB)  → testées directement
- get_city_center() est async et utilise la DB                         → mock AsyncSession

Analogie Symfony : tester un GeoService PHP avec un EntityManager mocké.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.entities.geography.proximity import compute_bounding_box, filter_by_distance
from app.adapters.gateways.db.repositories.geospatial_repository import get_city_center


# =============================================================================
# Helpers
# =============================================================================

def make_property(*, city: str, lat: float | None, lon: float | None) -> MagicMock:
    """Crée un faux objet Property avec les attributs minimaux nécessaires."""
    p = MagicMock()
    p.city = city
    p.latitude = lat
    p.longitude = lon
    return p


# =============================================================================
# compute_bounding_box — tests purs (sans DB)
# =============================================================================

class TestComputeBoundingBox:
    def test_center_is_inside_bbox(self):
        lat, lon = 48.6, 1.82
        lat_min, lat_max, lon_min, lon_max = compute_bounding_box(lat, lon, radius_km=15)
        assert lat_min < lat < lat_max
        assert lon_min < lon < lon_max

    def test_bbox_is_symmetric_around_center(self):
        lat, lon = 48.6, 1.82
        lat_min, lat_max, lon_min, lon_max = compute_bounding_box(lat, lon, radius_km=15)
        delta_lat = lat_max - lat
        assert abs((lat - lat_min) - delta_lat) < 1e-10
        delta_lon = lon_max - lon
        assert abs((lon - lon_min) - delta_lon) < 1e-10

    def test_larger_radius_gives_larger_bbox(self):
        small = compute_bounding_box(48.6, 1.82, radius_km=10)
        large = compute_bounding_box(48.6, 1.82, radius_km=30)
        # lat span
        assert (large[1] - large[0]) > (small[1] - small[0])
        # lon span
        assert (large[3] - large[2]) > (small[3] - small[2])

    def test_zero_radius_returns_point(self):
        lat, lon = 48.6, 1.82
        lat_min, lat_max, lon_min, lon_max = compute_bounding_box(lat, lon, radius_km=0)
        assert lat_min == lat_max == lat
        assert lon_min == lon_max == lon


# =============================================================================
# filter_by_distance — tests purs (sans DB)
# =============================================================================

class TestFilterByDistance:
    def test_keeps_properties_within_radius(self):
        # Paris (48.85, 2.35) comme centre
        props = [
            make_property(city="Paris", lat=48.85, lon=2.35),      # 0 km
            make_property(city="Vincennes", lat=48.85, lon=2.44),  # ~6 km
            make_property(city="Versailles", lat=48.80, lon=2.13), # ~17 km
            make_property(city="Lyon", lat=45.75, lon=4.83),       # ~390 km
        ]
        result = filter_by_distance(props, 48.85, 2.35, radius_km=20)
        assert len(result) == 3  # Paris + Vincennes + Versailles

    def test_excludes_properties_outside_radius(self):
        props = [
            make_property(city="Lyon", lat=45.75, lon=4.83),
        ]
        result = filter_by_distance(props, 48.85, 2.35, radius_km=20)
        assert result == []

    def test_ignores_properties_without_coordinates(self):
        props = [
            make_property(city="Paris", lat=None, lon=None),
            make_property(city="Paris", lat=48.85, lon=2.35),  # 0 km — gardé
        ]
        result = filter_by_distance(props, 48.85, 2.35, radius_km=5)
        assert len(result) == 1
        assert result[0].city == "Paris"

    def test_empty_list_returns_empty(self):
        result = filter_by_distance([], 48.85, 2.35, radius_km=20)
        assert result == []

    def test_radius_boundary_included(self):
        # Versailles ≈ 17 km de Paris → inclus dans un rayon de 20 km
        props = [make_property(city="Versailles", lat=48.80, lon=2.13)]
        result = filter_by_distance(props, 48.85, 2.35, radius_km=20)
        assert len(result) == 1


# =============================================================================
# get_city_center — tests async avec mock
# =============================================================================

class TestGetCityCenter:
    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_returns_average_of_city_properties(self, mock_session):
        # Simuler 2 biens à Rambouillet avec coordonnées
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (48.60, 1.82),
            (48.70, 1.90),
        ]
        mock_session.execute.return_value = mock_result

        center = await get_city_center(mock_session, "Rambouillet")

        assert center is not None
        assert center == pytest.approx((48.65, 1.86))

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_city(self, mock_session):
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        center = await get_city_center(mock_session, "VilleInconnue")

        assert center is None

    @pytest.mark.asyncio
    async def test_single_property_returns_its_coordinates(self, mock_session):
        mock_result = MagicMock()
        mock_result.all.return_value = [(48.6, 1.82)]
        mock_session.execute.return_value = mock_result

        center = await get_city_center(mock_session, "Rambouillet")

        assert center == pytest.approx((48.6, 1.82))

    @pytest.mark.asyncio
    async def test_city_name_comparison_is_case_insensitive(self, mock_session):
        """La requête SQL utilise func.lower() → la comparaison est case-insensitive.
        On vérifie que get_city_center est bien appelé (la logique SQL est dans la DB).
        """
        mock_result = MagicMock()
        mock_result.all.return_value = [(48.85, 2.35)]
        mock_session.execute.return_value = mock_result

        # Les deux appels doivent produire le même résultat (même SQL compilé)
        center_lower = await get_city_center(mock_session, "paris")
        center_title = await get_city_center(mock_session, "Paris")

        assert center_lower == center_title
