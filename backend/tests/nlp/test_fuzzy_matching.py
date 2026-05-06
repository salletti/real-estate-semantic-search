"""
Tests — fuzzy_matching.py (V2.4)
==================================

Stratégie de test :
- Tests unitaires purs sur find_closest_keyword
- Pas de dépendance au parser, pas de base de données
- Chaque cas couvre un comportement précis de l'algorithme Levenshtein

MENTAL MODEL :
    token  distance=0  → exact match (retourné si unique)
    token  distance=1  → 1 opération : insertion / suppression / substitution
    token  distance≥2  → rejeté (max_distance=1 par défaut)
    token  len≤2       → stop condition (jamais fuzzy-matché)
    token  → 2+ matches → ambiguïté → None
"""

import pytest

from app.entities.nlp.fuzzy_matching import _levenshtein, find_closest_keyword


class TestLevenshtein:
    """Tests bas-niveau de la fonction de distance."""

    def test_identical_strings(self):
        assert _levenshtein("villa", "villa") == 0

    def test_single_substitution(self):
        # "vilaa" → "villa" : 1 substitution (a→l à la position 4)
        assert _levenshtein("vilaa", "villa") == 1

    def test_single_insertion(self):
        # "apartement" → "appartement" : 1 insertion (ajouter 'p')
        assert _levenshtein("apartement", "appartement") == 1

    def test_single_deletion(self):
        # "apparttemnt" has 2 ops; simpler case: "villla" → "villa"
        assert _levenshtein("villla", "villa") == 1

    def test_empty_string(self):
        assert _levenshtein("", "villa") == 5
        assert _levenshtein("villa", "") == 5
        assert _levenshtein("", "") == 0

    def test_symmetric(self):
        assert _levenshtein("apartement", "appartement") == _levenshtein("appartement", "apartement")

    def test_distance_two(self):
        # "aprtement" vs "appartement": missing 'p' and 'a' → distance 2
        assert _levenshtein("aprtement", "appartement") == 2


class TestFindClosestKeyword:
    """Tests de la fonction principale de fuzzy matching."""

    # ── Distance 1 : les cas nominaux ────────────────────────────────────────

    def test_substitution_distance_1(self):
        # "vilaa" → "villa" (a→l)
        assert find_closest_keyword("vilaa", {"villa"}) == "villa"

    def test_insertion_distance_1(self):
        # "apartement" → "appartement" (insert 'p')
        assert find_closest_keyword("apartement", {"appartement"}) == "appartement"

    def test_deletion_distance_1(self):
        # "apparttemnt" → simpler: "maiosn" is distance 2 (transposition in Levenshtein)
        # Use "pavillon" → "paviillon" (extra 'i') at distance 1
        assert find_closest_keyword("paviillon", {"pavillon"}) == "pavillon"

    def test_exact_match_distance_zero(self):
        # Distance 0 ≤ max_distance=1 → retourné
        assert find_closest_keyword("villa", {"villa", "maison"}) == "villa"

    # ── Pas de match ─────────────────────────────────────────────────────────

    def test_too_far_distance_2(self):
        # "aprtement" vs "appartement" : distance 2 → None
        assert find_closest_keyword("aprtement", {"appartement"}) is None

    def test_no_match_unrelated_token(self):
        # "lumineux" n'est proche d'aucun keyword immobilier
        assert find_closest_keyword("lumineux", {"appartement", "villa", "maison"}) is None

    def test_empty_candidates(self):
        assert find_closest_keyword("appartement", set()) is None

    # ── Ambiguïté ────────────────────────────────────────────────────────────

    def test_ambiguous_multiple_matches(self):
        # "maisn" est à distance 1 de "maison" ET de "maisnn" → ambiguïté → None
        assert find_closest_keyword("maisn", {"maison", "maisnn"}) is None

    # ── Stop conditions ───────────────────────────────────────────────────────

    def test_short_token_2_chars_stop_condition(self):
        # "pa" ≤ 2 chars → jamais fuzzy-matché, même si "parking" est à distance 5
        assert find_closest_keyword("pa", {"parking", "paris"}) is None

    def test_short_token_1_char_stop_condition(self):
        assert find_closest_keyword("a", {"appartement"}) is None

    def test_token_3_chars_not_filtered(self):
        # 3 chars > 2 → fuzzy matching autorisé
        # "vll" vs "villa" (5) : distance 3 → None (pas dans max_distance=1)
        # Mais "box" vs "boxy" serait distance 1 → match
        assert find_closest_keyword("boxy", {"box"}) == "box"

    # ── Insensibilité à la casse ──────────────────────────────────────────────

    def test_case_insensitive_token(self):
        assert find_closest_keyword("VILAA", {"villa"}) == "villa"

    def test_case_insensitive_candidate(self):
        assert find_closest_keyword("vilaa", {"VILLA"}) == "VILLA"

    def test_case_insensitive_both(self):
        assert find_closest_keyword("VILAA", {"VILLA"}) == "VILLA"

    # ── max_distance personnalisé ────────────────────────────────────────────

    def test_custom_max_distance_0(self):
        # max_distance=0 : uniquement les matches exacts
        assert find_closest_keyword("vilaa", {"villa"}, max_distance=0) is None
        assert find_closest_keyword("villa", {"villa"}, max_distance=0) == "villa"

    def test_custom_max_distance_2(self):
        # max_distance=2 : "aprtement" (distance 2) est retourné s'il est unique
        assert find_closest_keyword("aprtement", {"appartement"}, max_distance=2) == "appartement"
