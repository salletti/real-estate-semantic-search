"""
Tests — parse_intent_using_llm (V4)

Tests synchrones. Le LLM (parse_intent_with_llm) est mocké via pytest-mock.
On teste les décisions du gate et la propagation du résultat final.
"""

import pytest

from app.entities.nlp.llm_intent_schema import LlmIntentResponse
from app.entities.nlp.intent_parser import parse_intent_using_llm
from app.entities.nlp.intent_schema import (
    IntentType,
    PropertyType,
    TransactionType,
)

_MOCK_PATH = "app.entities.nlp.intent_parser.parse_intent_with_llm"


# =============================================================================
# Gate bloque le LLM (2 signaux forts)
# =============================================================================


class TestParseIntentV4NoLlm:
    """Le gate détecte 2 signaux forts → LLM jamais appelé."""

    def test_fallback_no_llm(self, mocker):
        # "appartement paris" → city + property_type → gate False
        mock_llm = mocker.patch(_MOCK_PATH)
        result = parse_intent_using_llm("appartement paris")
        mock_llm.assert_not_called()
        assert result.property_type == PropertyType.apartment
        assert result.city == "Paris"

    def test_no_llm_city_and_max_price(self, mocker):
        # city + max_price → gate False
        mock_llm = mocker.patch(_MOCK_PATH)
        result = parse_intent_using_llm("maison lyon sous 300k")
        mock_llm.assert_not_called()
        assert result.city == "Lyon"
        assert result.max_price == 300000


# =============================================================================
# Gate laisse passer le LLM + enrichissement
# =============================================================================


class TestParseIntentV4LlmEnrichment:
    """Le gate détecte une ambiguïté → LLM appelé et résultat mergé."""

    def test_llm_enrichment(self, mocker):
        # "logement bordeaux lumineux" → rule parser detects city=Bordeaux (1 signal)
        # → gate True → LLM fills property_type
        # The validator keeps city because "bordeaux" is present in the query.
        mock_llm = mocker.patch(
            _MOCK_PATH,
            return_value=LlmIntentResponse(
                property_type=PropertyType.apartment,
                city="Bordeaux",
                semantic_terms=["lumineux"],
            ),
        )
        result = parse_intent_using_llm("logement bordeaux lumineux")
        mock_llm.assert_called_once()
        assert result.property_type == PropertyType.apartment
        assert result.city == "Bordeaux"
        assert "lumineux" in result.semantic_terms
        assert result.intent == IntentType.property_search

    def test_typo_correction(self, mocker):
        # "aprtement paris" → typo détectée → gate True, LLM corrige property_type
        mock_llm = mocker.patch(
            _MOCK_PATH,
            return_value=LlmIntentResponse(
                property_type=PropertyType.apartment,
                semantic_terms=["standard"],
            ),
        )
        result = parse_intent_using_llm("aprtement paris")
        mock_llm.assert_called_once()
        assert result.property_type == PropertyType.apartment
        # city détectée par rule parser → conservée
        assert result.city == "Paris"


# =============================================================================
# Dégradation gracieuse — LLM échoue → rule intent retourné
# =============================================================================


class TestParseIntentV4LlmFailure:
    """Si le LLM retourne None → parse_intent_using_llm retourne le résultat du rule parser."""

    def test_llm_failure_fallback(self, mocker):
        mocker.patch(_MOCK_PATH, return_value=None)
        result = parse_intent_using_llm("logement sympa pas cher")
        # Rule parser seul → intent=unknown, aucun champ structurel
        assert result.intent == IntentType.unknown
        assert result.city is None
        assert result.property_type is None

    def test_llm_exception_does_not_propagate(self, mocker):
        # L'exception est attrapée dans llm_intent_service → retourne None
        # On simule ici que parse_intent_with_llm retourne None (comportement post-catch)
        mocker.patch(_MOCK_PATH, return_value=None)
        # Ne doit pas lever d'exception
        result = parse_intent_using_llm("quelque chose d'impossible à parser")
        assert result is not None
