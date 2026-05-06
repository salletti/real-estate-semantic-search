"""
Tests — confidence_gate.py (V4)

Philosophie : tests purs sans mock, sans LLM, sans base de données.
Chaque test vérifie une règle précise du gate ou de la détection de typo.
"""

import pytest

from app.entities.nlp.confidence_gate import has_possible_typo, should_use_llm
from app.entities.nlp.intent_schema import (
    IntentType,
    PropertyIntent,
    PropertyType,
    TransactionType,
)


# =============================================================================
# has_possible_typo
# =============================================================================


class TestHasPossibleTypo:
    """Vérifie la détection de tokens à distance Levenshtein = 2 des keywords."""

    def test_aprtement_is_typo(self):
        # "aprtement" (9) vs "appartement" (11) : distance 2 → True
        assert has_possible_typo("aprtement paris") is True

    def test_miason_is_typo(self):
        # "miason" vs "maison" : i/a transposés → distance 2 (standard Levenshtein)
        # Distance 1 (e.g. "masson") est gérée par le rule parser → pas un cas LLM
        assert has_possible_typo("miason bordeaux") is True

    def test_lumineux_is_not_typo(self):
        # "lumineux" est un terme sémantique valide, loin de tout keyword structurel
        assert has_possible_typo("appartement lumineux") is False

    def test_calme_is_not_typo(self):
        # "calme" est sémantique
        assert has_possible_typo("maison calme jardin") is False

    def test_short_token_ignored(self):
        # Tokens < 5 chars ne peuvent pas être des typos de keywords longs
        assert has_possible_typo("app pa") is False

    def test_empty_query(self):
        assert has_possible_typo("") is False

    def test_only_city_no_typo(self):
        # "paris" n'est pas proche d'un keyword structurel de _STRUCTURAL_TOKENS
        assert has_possible_typo("paris") is False

    def test_well_typed_query_no_typo(self):
        assert has_possible_typo("appartement paris sous 500k") is False


# =============================================================================
# should_use_llm — Phase 1 : No LLM (2 signaux forts)
# =============================================================================


class TestGateNoLlm:
    """Vérifie que le gate retourne False quand deux signaux structurés sont présents."""

    def test_city_and_property_type_no_llm(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            city="Paris",
            property_type=PropertyType.apartment,
        )
        use_llm, reason = should_use_llm(intent, "appartement paris")
        assert use_llm is False
        assert "city + property_type" in reason

    def test_city_and_max_price_no_llm(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            city="Lyon",
            max_price=300000,
        )
        use_llm, reason = should_use_llm(intent, "maison lyon sous 300k")
        assert use_llm is False
        assert "city + max_price" in reason

    def test_property_type_and_transaction_no_llm(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            property_type=PropertyType.house,
            transaction_type=TransactionType.sale,
        )
        use_llm, reason = should_use_llm(intent, "maison a vendre")
        assert use_llm is False
        assert "property_type + transaction_type" in reason

    def test_returns_reason_string(self):
        intent = PropertyIntent(city="Paris", property_type=PropertyType.studio)
        _, reason = should_use_llm(intent, "studio paris")
        assert isinstance(reason, str)
        assert len(reason) > 0


# =============================================================================
# should_use_llm — Phase 2 : Use LLM (ambiguïté)
# =============================================================================


class TestGateUseLlm:
    """Vérifie que le gate retourne True dans les cas d'ambiguïté."""

    def test_unknown_intent_uses_llm(self):
        # Aucun signal → intent=unknown
        intent = PropertyIntent()  # all defaults, intent=unknown
        use_llm, reason = should_use_llm(intent, "quelque chose de sympa")
        assert use_llm is True
        assert "unknown" in reason

    def test_possible_typo_uses_llm(self):
        # "aprtement" → distance 2 de "appartement" → gate True
        intent = PropertyIntent(
            intent=IntentType.property_search,
            city="Paris",
        )
        use_llm, reason = should_use_llm(intent, "aprtement paris")
        assert use_llm is True
        assert "typo" in reason

    def test_city_only_uses_llm(self):
        # city détectée mais pas property_type → possible typo non rattrapé
        intent = PropertyIntent(
            intent=IntentType.property_search,
            city="Lyon",
        )
        use_llm, reason = should_use_llm(intent, "maison lyon")
        # "maison" est détecté, donc property_type=house, mais ici on simule
        # un intent avec city seulement (e.g. la query avait une faute)
        # Note: avec city=Lyon et property_type=None → True
        assert use_llm is True

    def test_property_type_only_uses_llm(self):
        # property_type mais pas city → possible city mal orthographiée
        intent = PropertyIntent(
            intent=IntentType.property_search,
            property_type=PropertyType.apartment,
        )
        use_llm, reason = should_use_llm(intent, "appartement lyo")
        assert use_llm is True

    def test_no_fields_uses_llm(self):
        # Aucun champ structurel
        intent = PropertyIntent(
            intent=IntentType.property_search,
            semantic_terms=["familial"],
        )
        use_llm, reason = should_use_llm(intent, "logement familial")
        assert use_llm is True

    def test_long_query_uses_llm(self):
        # No city/property_type → skips typo/unknown/city-only conditions,
        # reaches the >12 token check (13 tokens here).
        intent = PropertyIntent(intent=IntentType.property_search)
        long_query = "je cherche un grand logement avec vue sur jardin lumineux calme proche transport"
        use_llm, reason = should_use_llm(intent, long_query)
        assert use_llm is True
        assert "token" in reason

    def test_many_semantic_terms_uses_llm(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            semantic_terms=["lumineux", "calme", "moderne", "terrasse", "jardin"],
        )
        use_llm, reason = should_use_llm(intent, "logement lumineux calme moderne terrasse jardin")
        assert use_llm is True
        assert "semantic" in reason
