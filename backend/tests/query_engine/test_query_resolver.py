"""
Tests — Query Resolver V1
==========================

Vérifie que resolve_query() prend la bonne décision de stratégie
pour chaque combinaison d'intent.

ANALOGIE SYMFONY
-----------------
Ces tests correspondent aux tests unitaires d'un Resolver Symfony :
on injecte un DTO d'entrée, on vérifie le DTO de sortie.
Aucune DB, aucune dépendance externe — test pur de logique métier.
"""

import pytest

from app.entities.nlp.intent_schema import (
    IntentType,
    MandateType,
    PropertyIntent,
    PropertyType,
    TransactionType,
)
from app.entities.search.query_resolver import resolve_query
from app.entities.search.query_types import QueryStrategy


class TestSqlOnly:
    """Intent avec filtres structurés et sans termes sémantiques → sql_only."""

    def test_city_filter(self):
        intent = PropertyIntent(intent=IntentType.property_search, city="Paris")
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.sql_only
        assert resolution.has_structured_filters is True
        assert resolution.has_semantic_terms is False

    def test_price_filter(self):
        intent = PropertyIntent(intent=IntentType.property_search, max_price=500_000)
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.sql_only
        assert resolution.has_structured_filters is True

    def test_multiple_structured_filters(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            city="Lyon",
            property_type=PropertyType.apartment,
            max_price=300_000,
            min_rooms=3,
            mandate_type=MandateType.exclusive,
            transaction_type=TransactionType.sale,
        )
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.sql_only
        assert resolution.has_structured_filters is True
        assert resolution.has_semantic_terms is False

    def test_min_rooms_alone(self):
        intent = PropertyIntent(intent=IntentType.property_search, min_rooms=4)
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.sql_only

    def test_mandate_type_alone(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            mandate_type=MandateType.simple,
        )
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.sql_only

    def test_transaction_type_alone(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            transaction_type=TransactionType.rental,
        )
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.sql_only


class TestSemanticOnly:
    """Intent avec termes sémantiques et sans filtres structurés → semantic_only."""

    def test_single_semantic_term(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            semantic_terms=["lumineux"],
        )
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.semantic_only
        assert resolution.has_structured_filters is False
        assert resolution.has_semantic_terms is True

    def test_multiple_semantic_terms(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            semantic_terms=["lumineux", "calme", "vue dégagée"],
        )
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.semantic_only
        assert resolution.has_semantic_terms is True

    def test_reason_mentions_semantic(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            semantic_terms=["proche écoles"],
        )
        resolution = resolve_query(intent)

        assert "semantic" in resolution.reason


class TestHybrid:
    """Intent avec filtres structurés ET termes sémantiques → hybrid."""

    def test_city_plus_semantic(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            city="Bordeaux",
            semantic_terms=["avec jardin"],
        )
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.hybrid
        assert resolution.has_structured_filters is True
        assert resolution.has_semantic_terms is True

    def test_price_and_type_plus_semantic(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            property_type=PropertyType.house,
            max_price=400_000,
            semantic_terms=["lumineux", "calme"],
        )
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.hybrid

    def test_all_fields_hybrid(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            city="Marseille",
            property_type=PropertyType.villa,
            max_price=800_000,
            min_rooms=5,
            transaction_type=TransactionType.sale,
            semantic_terms=["piscine", "vue mer"],
        )
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.hybrid
        assert resolution.has_structured_filters is True
        assert resolution.has_semantic_terms is True

    def test_reason_mentions_hybrid(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            city="Nice",
            semantic_terms=["calme"],
        )
        resolution = resolve_query(intent)

        assert "hybrid" in resolution.reason


class TestNearby:
    """Intent avec nearby_city + search_radius_km → nearby (prioritaire)."""

    def test_nearby_only(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            nearby_city="Paris",
            search_radius_km=15,
        )
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.nearby
        assert resolution.has_structured_filters is True
        assert resolution.has_semantic_terms is False

    def test_nearby_plus_semantic_terms(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            nearby_city="Lyon",
            search_radius_km=20,
            semantic_terms=["lumineux", "calme"],
        )
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.nearby
        assert resolution.has_structured_filters is True
        assert resolution.has_semantic_terms is True

    def test_nearby_plus_other_structured_filters(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            nearby_city="Bordeaux",
            search_radius_km=10,
            property_type=PropertyType.house,
            max_price=450_000,
            min_rooms=4,
        )
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.nearby
        assert resolution.has_structured_filters is True

    def test_nearby_reason_mentions_nearby(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            nearby_city="Nice",
            search_radius_km=12,
        )
        resolution = resolve_query(intent)

        assert "nearby" in resolution.reason


class TestEmptyFallback:
    """Intent vide ou non reconnu → sql_only (fallback safe)."""

    def test_completely_empty_intent(self):
        intent = PropertyIntent()
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.sql_only
        assert resolution.has_structured_filters is False
        assert resolution.has_semantic_terms is False

    def test_unknown_intent_no_fields(self):
        intent = PropertyIntent(intent=IntentType.unknown)
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.sql_only

    def test_empty_semantic_terms_list(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            semantic_terms=[],
        )
        resolution = resolve_query(intent)

        assert resolution.strategy == QueryStrategy.sql_only
        assert resolution.has_semantic_terms is False

    def test_fallback_reason_is_explicit(self):
        intent = PropertyIntent()
        resolution = resolve_query(intent)

        assert "fallback" in resolution.reason
