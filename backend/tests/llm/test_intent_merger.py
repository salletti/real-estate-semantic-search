"""
Tests — intent_merger.py (V4)

Tests purs : fonctions synchrones, pas de LLM, pas de mock.
Chaque test vérifie une règle de priorité du merge.
"""

import pytest

from app.entities.nlp.intent_merger import merge_intents
from app.entities.nlp.llm_intent_schema import LlmIntentResponse
from app.entities.nlp.intent_schema import (
    IntentType,
    PropertyIntent,
    PropertyType,
    TransactionType,
)


# =============================================================================
# Priorité : Rule wins sur champs stricts
# =============================================================================


class TestMergerStrictPriority:
    """Rule parser gagne toujours sur les champs stricts déjà renseignés."""

    def test_rule_city_wins_over_llm(self):
        rule = PropertyIntent(city="Paris", property_type=PropertyType.apartment)
        llm = LlmIntentResponse(city="Lyon")
        merged = merge_intents(rule, llm)
        assert merged.city == "Paris"

    def test_rule_max_price_wins(self):
        rule = PropertyIntent(max_price=400000)
        llm = LlmIntentResponse(max_price=600000)
        merged = merge_intents(rule, llm)
        assert merged.max_price == 400000

    def test_rule_property_type_wins(self):
        rule = PropertyIntent(property_type=PropertyType.house)
        llm = LlmIntentResponse(property_type=PropertyType.apartment)
        merged = merge_intents(rule, llm)
        assert merged.property_type == PropertyType.house

    def test_rule_transaction_type_wins(self):
        rule = PropertyIntent(transaction_type=TransactionType.sale)
        llm = LlmIntentResponse(transaction_type=TransactionType.rental)
        merged = merge_intents(rule, llm)
        assert merged.transaction_type == TransactionType.sale


# =============================================================================
# LLM remplit les trous (champs None)
# =============================================================================


class TestMergerLlmFillsGaps:
    """LLM enrichit les champs que le rule parser n'a pas détectés."""

    def test_llm_fills_property_type(self):
        rule = PropertyIntent(city="Paris")  # property_type=None
        llm = LlmIntentResponse(property_type=PropertyType.house)
        merged = merge_intents(rule, llm)
        assert merged.property_type == PropertyType.house
        assert merged.city == "Paris"  # rule préservé

    def test_llm_fills_city(self):
        rule = PropertyIntent(property_type=PropertyType.apartment)
        llm = LlmIntentResponse(city="Lyon")
        merged = merge_intents(rule, llm)
        assert merged.city == "Lyon"

    def test_llm_fills_transaction_type(self):
        rule = PropertyIntent()
        llm = LlmIntentResponse(transaction_type=TransactionType.rental)
        merged = merge_intents(rule, llm)
        assert merged.transaction_type == TransactionType.rental


# =============================================================================
# Semantic terms : UNION sans doublons
# =============================================================================


class TestMergerSemanticTerms:
    """Les semantic_terms sont la union des deux sources, sans doublons."""

    def test_semantic_union_no_duplicates(self):
        rule = PropertyIntent(semantic_terms=["calme", "lumineux"])
        llm = LlmIntentResponse(semantic_terms=["lumineux", "budget"])
        merged = merge_intents(rule, llm)
        assert "calme" in merged.semantic_terms
        assert "lumineux" in merged.semantic_terms
        assert "budget" in merged.semantic_terms
        assert merged.semantic_terms.count("lumineux") == 1  # pas de doublon

    def test_llm_adds_new_terms(self):
        rule = PropertyIntent(semantic_terms=[])
        llm = LlmIntentResponse(semantic_terms=["familial", "budget"])
        merged = merge_intents(rule, llm)
        assert merged.semantic_terms == ["familial", "budget"]

    def test_rule_terms_preserved_if_llm_empty(self):
        rule = PropertyIntent(semantic_terms=["lumineux"])
        llm = LlmIntentResponse(semantic_terms=[])
        merged = merge_intents(rule, llm)
        assert merged.semantic_terms == ["lumineux"]


# =============================================================================
# Re-déduction de l'intent après merge
# =============================================================================


class TestMergerIntentRededuction:
    """L'intent est re-déduit seulement s'il était unknown avant le merge."""

    def test_intent_rededuced_when_property_added(self):
        # Rule: unknown, LLM ajoute property_type → property_search
        rule = PropertyIntent(intent=IntentType.unknown)
        llm = LlmIntentResponse(property_type=PropertyType.apartment)
        merged = merge_intents(rule, llm)
        assert merged.intent == IntentType.property_search

    def test_intent_rededuced_when_city_added(self):
        rule = PropertyIntent(intent=IntentType.unknown)
        llm = LlmIntentResponse(city="Paris")
        merged = merge_intents(rule, llm)
        assert merged.intent == IntentType.property_search

    def test_intent_stays_unknown_if_only_semantic(self):
        # LLM ajoute uniquement semantic_terms → pas de promotion à property_search
        # Comportement voulu : requête purement sémantique → semantic search
        rule = PropertyIntent(intent=IntentType.unknown)
        llm = LlmIntentResponse(semantic_terms=["sympa", "familial"])
        merged = merge_intents(rule, llm)
        assert merged.intent == IntentType.unknown

    def test_intent_rental_when_transaction_rental(self):
        rule = PropertyIntent(intent=IntentType.unknown)
        llm = LlmIntentResponse(transaction_type=TransactionType.rental)
        merged = merge_intents(rule, llm)
        assert merged.intent == IntentType.rental_search

    def test_rule_intent_preserved_when_already_set(self):
        # Rule a rental_search → le merge ne doit pas le changer
        rule = PropertyIntent(
            intent=IntentType.rental_search,
            transaction_type=TransactionType.rental,
        )
        llm = LlmIntentResponse(property_type=PropertyType.studio, city="Bordeaux")
        merged = merge_intents(rule, llm)
        assert merged.intent == IntentType.rental_search

    def test_intent_property_search_when_sale_transaction(self):
        # transaction_type=sale → property_search (même sans city/property_type)
        rule = PropertyIntent(intent=IntentType.unknown)
        llm = LlmIntentResponse(transaction_type=TransactionType.sale)
        merged = merge_intents(rule, llm)
        assert merged.intent == IntentType.property_search
