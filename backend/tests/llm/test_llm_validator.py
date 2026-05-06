"""
Tests — llm_validator.py (V4)

Tests purs : pas de LLM, pas de mock, pas de DB.
Chaque test vérifie une règle de validation anti-hallucination.
"""

import pytest

from app.entities.nlp.llm_intent_schema import LlmIntentResponse
from app.entities.nlp.llm_validator import validate_llm_response
from app.entities.nlp.intent_schema import PropertyType, TransactionType


# =============================================================================
# Champs STRICTS — rejetés si non fondés
# =============================================================================


class TestValidatorStrictFields:
    """Vérifie que les champs stricts sont rejetés si absents de la query."""

    # ── max_price ─────────────────────────────────────────────────────────────

    def test_invented_price_rejected(self):
        # Aucun chiffre dans la query → max_price inventé → rejeté
        llm = LlmIntentResponse(max_price=500000, confidence_score=0.8)
        result = validate_llm_response(llm, "appartement familial")
        assert result.max_price is None

    def test_explicit_price_kept(self):
        # Chiffre présent → max_price potentiellement fondé → conservé
        llm = LlmIntentResponse(max_price=500000, confidence_score=0.9)
        result = validate_llm_response(llm, "appartement sous 500k")
        assert result.max_price == 500000

    def test_price_with_digits_in_rooms_kept(self):
        # Le chiffre peut venir des pièces — V1 conserve le prix si digit présent
        # Limite documentée : on ne distingue pas "3 pièces" de "300k" en V1
        llm = LlmIntentResponse(max_price=300000, confidence_score=0.7)
        result = validate_llm_response(llm, "appartement 3 pieces")
        assert result.max_price == 300000  # digit trouvé → conservé (V1 limitation)

    # ── min_rooms ─────────────────────────────────────────────────────────────

    def test_invented_rooms_rejected(self):
        llm = LlmIntentResponse(min_rooms=3, confidence_score=0.6)
        result = validate_llm_response(llm, "maison familiale calme")
        assert result.min_rooms is None

    def test_explicit_rooms_kept(self):
        llm = LlmIntentResponse(min_rooms=3, confidence_score=0.9)
        result = validate_llm_response(llm, "appartement 3 pieces bordeaux")
        assert result.min_rooms == 3

    # ── city ──────────────────────────────────────────────────────────────────

    def test_invented_city_rejected(self):
        # "Paris" absent de la query → rejeté
        llm = LlmIntentResponse(city="Paris", confidence_score=0.5)
        result = validate_llm_response(llm, "appartement familial lumineux")
        assert result.city is None

    def test_explicit_city_kept(self):
        # "lyon" présent dans la query → conservé
        llm = LlmIntentResponse(city="Lyon", confidence_score=0.9)
        result = validate_llm_response(llm, "appartement vers lyon pas cher")
        assert result.city == "Lyon"

    def test_city_accent_kept(self):
        # "Aix-en-Provence" → "aix" dans la query normalisée → conservé
        llm = LlmIntentResponse(city="Aix-en-Provence", confidence_score=0.85)
        result = validate_llm_response(llm, "villa près d'aix avec piscine")
        assert result.city == "Aix-en-Provence"

    def test_city_case_insensitive(self):
        llm = LlmIntentResponse(city="MARSEILLE", confidence_score=0.9)
        result = validate_llm_response(llm, "studio marseille bord de mer")
        assert result.city == "MARSEILLE"


# =============================================================================
# Champs SOUPLES — toujours conservés
# =============================================================================


class TestValidatorSoftFields:
    """Vérifie que les champs souples ne sont jamais rejetés par le validator."""

    def test_property_type_always_kept(self):
        # Correction de typo : property_type est toujours conservé
        llm = LlmIntentResponse(
            property_type=PropertyType.apartment,
            confidence_score=0.9,
        )
        result = validate_llm_response(llm, "aprtement lumineux")
        assert result.property_type == PropertyType.apartment

    def test_transaction_type_always_kept(self):
        llm = LlmIntentResponse(
            transaction_type=TransactionType.rental,
            confidence_score=0.8,
        )
        result = validate_llm_response(llm, "logement à louer sympa")
        assert result.transaction_type == TransactionType.rental

    def test_semantic_terms_always_kept(self):
        # L'enrichissement sémantique n'est jamais rejeté
        llm = LlmIntentResponse(
            semantic_terms=["familial", "budget", "calme"],
            confidence_score=0.7,
        )
        result = validate_llm_response(llm, "logement pas trop cher pour famille")
        assert result.semantic_terms == ["familial", "budget", "calme"]

    def test_semantic_enrichment_without_city_is_ok(self):
        # LLM enrichit semantic_terms mais invente Paris → prix OK, city rejeté
        llm = LlmIntentResponse(
            city="Paris",
            semantic_terms=["budget", "lumineux"],
            confidence_score=0.6,
        )
        result = validate_llm_response(llm, "logement pas cher lumineux")
        assert result.city is None  # inventé → rejeté
        assert "budget" in result.semantic_terms  # sémantique → conservé
        assert "lumineux" in result.semantic_terms

    def test_all_none_returns_unchanged(self):
        llm = LlmIntentResponse(confidence_score=0.0, explanation="no data")
        result = validate_llm_response(llm, "bonjour")
        assert result.city is None
        assert result.max_price is None
        assert result.property_type is None
        assert result.semantic_terms == []
