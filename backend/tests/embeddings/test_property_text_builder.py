"""
Tests — property_text_builder.py
==================================

build_semantic_text() est une fonction pure (aucune I/O).
On construit des MagicMock qui imitent Property et Description
sans toucher à SQLAlchemy ni à une vraie base de données.

Analogie PHP/PHPUnit :
    $prop = $this->createMock(Property::class);
    $prop->method('getType')->willReturn('house');
    // → Python : MagicMock avec attributs assignés directement
"""

from unittest.mock import MagicMock

import pytest

from app.entities.embeddings.text_builder import build_semantic_text


def _make_property(
    type_: str = "house",
    city: str = "Paris",
    rooms_count: int | None = 3,
    mandate_price: float | None = 450000.0,
    description: str | None = "Bel appartement lumineux.",
) -> MagicMock:
    """Fabrique un faux Property avec les attributs nécessaires à build_semantic_text."""
    prop = MagicMock()
    prop.type = type_
    prop.city = city
    prop.rooms_count = rooms_count
    prop.mandate_price = mandate_price

    if description is not None:
        desc = MagicMock()
        desc.description = description
        prop.descriptions = [desc]
    else:
        prop.descriptions = []

    return prop


class TestBuildSemanticText:
    def test_full_property_includes_all_fields(self):
        """Texte complet : type + city + pièces + prix + description."""
        prop = _make_property(
            type_="house",
            city="Paris",
            rooms_count=4,
            mandate_price=500000.0,
            description="Belle maison avec jardin.",
        )
        text = build_semantic_text(prop)
        assert "house" in text
        assert "Paris" in text
        assert "4 pièces" in text
        assert "500000€" in text
        assert "Belle maison avec jardin." in text

    def test_property_without_descriptions_omits_description(self):
        """Aucune description → texte sans partie description, pas de crash."""
        prop = _make_property(description=None)
        text = build_semantic_text(prop)
        assert text != ""
        assert "house" in text
        assert "Paris" in text

    def test_property_without_rooms_count_omits_pieces(self):
        """rooms_count=None → '… pièces' absent du texte."""
        prop = _make_property(rooms_count=None)
        text = build_semantic_text(prop)
        assert "pièces" not in text

    def test_property_without_price_omits_euros(self):
        """mandate_price=None → '€' absent du texte."""
        prop = _make_property(mandate_price=None)
        text = build_semantic_text(prop)
        assert "€" not in text

    def test_result_is_non_empty_stripped_string(self):
        """Le résultat est une chaîne non vide, sans espaces de tête/queue."""
        prop = _make_property()
        text = build_semantic_text(prop)
        assert isinstance(text, str)
        assert text == text.strip()
        assert len(text) > 0

    def test_minimal_property_only_type_city(self):
        """Propriété avec seulement type + city → texte minimal cohérent."""
        prop = _make_property(rooms_count=None, mandate_price=None, description=None)
        text = build_semantic_text(prop)
        assert text == "house Paris"

    def test_price_is_integer_formatted(self):
        """Le prix est formaté en entier (450000.0 → '450000€', pas '450000.0€')."""
        prop = _make_property(mandate_price=450000.0)
        text = build_semantic_text(prop)
        assert "450000€" in text
        assert "450000.0€" not in text
