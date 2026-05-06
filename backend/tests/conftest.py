import pytest

from app.entities.nlp.intent_schema import PropertyIntent, PropertyType


@pytest.fixture
def basic_intent():
    """Intent complet avec city, type et prix — utilisable dans plusieurs tests."""
    return PropertyIntent(
        city="Paris",
        property_type=PropertyType.house,
        max_price=500_000,
    )


@pytest.fixture
def empty_intent():
    """Intent vide — aucun champ renseigné."""
    return PropertyIntent()
