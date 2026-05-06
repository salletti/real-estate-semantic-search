"""
Tests unitaires — intent_schema.py

Stratégie : tests purs Pydantic, sans DB, sans async.
Vérifie que le schéma se comporte comme un DTO Symfony :
  - valeurs par défaut correctes
  - validation des types et des enums
  - coercition str → int
"""

import pytest
from pydantic import ValidationError

from app.entities.nlp.intent_schema import (
    IntentType,
    MandateType,
    PropertyIntent,
    PropertyType,
    TransactionType,
)


class TestIntentType:
    def test_str_enum_values(self):
        """str, Enum : la valeur de l'enum EST la chaîne — comme un PHP backed enum."""
        assert IntentType.property_search == "property_search"
        assert IntentType.mandate_search == "mandate_search"
        assert IntentType.rental_search == "rental_search"
        assert IntentType.unknown == "unknown"

    def test_all_four_values_defined(self):
        values = {e.value for e in IntentType}
        assert values == {"property_search", "mandate_search", "rental_search", "unknown"}


class TestPropertyType:
    def test_str_enum_values(self):
        assert PropertyType.house == "house"
        assert PropertyType.apartment == "apartment"
        assert PropertyType.studio == "studio"

    def test_eight_types_defined(self):
        assert len(PropertyType) == 8


class TestTransactionType:
    def test_values(self):
        assert TransactionType.sale == "sale"
        assert TransactionType.rental == "rental"


class TestMandateType:
    def test_values(self):
        assert MandateType.exclusive == "exclusive"
        assert MandateType.simple == "simple"


class TestPropertyIntentDefaults:
    def test_default_intent_is_unknown(self):
        intent = PropertyIntent()
        assert intent.intent == IntentType.unknown

    def test_all_optional_fields_are_none(self):
        intent = PropertyIntent()
        assert intent.city is None
        assert intent.property_type is None
        assert intent.max_price is None
        assert intent.min_rooms is None
        assert intent.mandate_type is None
        assert intent.transaction_type is None
        assert intent.published_more_than_days is None
        assert intent.published_less_than_days is None
        assert intent.agent_name is None

    def test_semantic_terms_default_empty_list(self):
        intent = PropertyIntent()
        assert intent.semantic_terms == []
        # Chaque instance a sa propre liste — pas de partage de référence
        assert PropertyIntent().semantic_terms is not PropertyIntent().semantic_terms


class TestPropertyIntentValidation:
    def test_invalid_intent_raises_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            PropertyIntent(intent="valeur_invalide")
        assert "property_search" in str(exc_info.value)

    def test_invalid_property_type_raises_validation_error(self):
        with pytest.raises(ValidationError):
            PropertyIntent(property_type="chalet")

    def test_invalid_transaction_type_raises_validation_error(self):
        with pytest.raises(ValidationError):
            PropertyIntent(transaction_type="troc")

    def test_price_str_to_int_coercion(self):
        """Pydantic coerce str → int automatiquement (équivalent de cast PHP)."""
        intent = PropertyIntent(max_price="500000")
        assert intent.max_price == 500_000
        assert isinstance(intent.max_price, int)

    def test_non_numeric_price_raises_validation_error(self):
        with pytest.raises(ValidationError):
            PropertyIntent(max_price="cher")


class TestPropertyIntentConstruction:
    def test_full_construction(self):
        intent = PropertyIntent(
            intent=IntentType.property_search,
            city="Paris",
            property_type=PropertyType.house,
            max_price=500_000,
            min_rooms=3,
            mandate_type=MandateType.exclusive,
            transaction_type=TransactionType.sale,
            published_more_than_days=30,
            published_less_than_days=7,
            agent_name="Marie Dupont",
            semantic_terms=["lumineux", "calme"],
        )
        assert intent.intent == IntentType.property_search
        assert intent.city == "Paris"
        assert intent.property_type == PropertyType.house
        assert intent.max_price == 500_000
        assert intent.min_rooms == 3
        assert intent.mandate_type == MandateType.exclusive
        assert intent.transaction_type == TransactionType.sale
        assert intent.published_more_than_days == 30
        assert intent.published_less_than_days == 7
        assert intent.agent_name == "Marie Dupont"
        assert intent.semantic_terms == ["lumineux", "calme"]

    def test_model_dump_produces_string_values(self):
        """model_dump() retourne les valeurs enum en str — prêt pour JSON."""
        intent = PropertyIntent(
            intent=IntentType.property_search,
            property_type=PropertyType.apartment,
        )
        data = intent.model_dump()
        assert data["intent"] == "property_search"
        assert data["property_type"] == "apartment"


class TestHasStructuredFilters:
    def test_empty_intent_has_no_filters(self):
        assert PropertyIntent().has_structured_filters() is False

    def test_city_alone_is_sufficient(self):
        assert PropertyIntent(city="Paris").has_structured_filters() is True

    def test_published_more_than_days_is_sufficient(self):
        assert PropertyIntent(published_more_than_days=30).has_structured_filters() is True

    def test_published_less_than_days_is_sufficient(self):
        assert PropertyIntent(published_less_than_days=7).has_structured_filters() is True

    def test_agent_name_is_sufficient(self):
        assert PropertyIntent(agent_name="Marie Dupont").has_structured_filters() is True
