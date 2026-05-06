"""
Tests — similarity.py
======================

cosine_similarity() est une fonction pure (zéro I/O) — testable directement,
sans mock ni fixture async.

Propriétés mathématiques vérifiées :
    - Vecteurs identiques → 1.0
    - Vecteurs orthogonaux → 0.0
    - Vecteurs nuls → 0.0 (guard anti-division)
    - Symétrie : sim(a,b) == sim(b,a)
    - Valeur pour vecteurs normalisés = dot product
"""

import math

import pytest

from app.entities.embeddings.similarity import cosine_similarity


class TestCosineSimilarity:
    def test_identical_vectors_return_one(self):
        """sim(a, a) == 1.0 pour tout vecteur non nul."""
        vec = [0.5, 0.5, 0.5, 0.5]
        result = cosine_similarity(vec, vec)
        assert math.isclose(result, 1.0, abs_tol=1e-6)

    def test_orthogonal_vectors_return_zero(self):
        """Vecteurs orthogonaux → angle 90° → cosine = 0."""
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        result = cosine_similarity(a, b)
        assert math.isclose(result, 0.0, abs_tol=1e-6)

    def test_opposite_vectors_return_minus_one(self):
        """Vecteurs opposés → angle 180° → cosine = -1."""
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        result = cosine_similarity(a, b)
        assert math.isclose(result, -1.0, abs_tol=1e-6)

    def test_zero_vector_a_returns_zero_safely(self):
        """Vecteur nul : guard anti-division-par-zéro → 0.0."""
        result = cosine_similarity([0.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        assert result == 0.0

    def test_zero_vector_b_returns_zero_safely(self):
        result = cosine_similarity([1.0, 0.0, 0.0], [0.0, 0.0, 0.0])
        assert result == 0.0

    def test_symmetry(self):
        """sim(a, b) == sim(b, a) — propriété de symétrie."""
        a = [0.1, 0.9, 0.3]
        b = [0.8, 0.2, 0.5]
        assert cosine_similarity(a, b) == cosine_similarity(b, a)

    def test_returns_float(self):
        result = cosine_similarity([1.0, 0.0], [0.5, 0.5])
        assert isinstance(result, float)

    def test_normalized_vectors_equal_dot_product(self):
        """Vecteurs L2-normalisés : cosine = dot product (propriété utilisée par embed_text)."""
        import math
        a = [1.0 / math.sqrt(2), 1.0 / math.sqrt(2)]
        b = [1.0 / math.sqrt(2), 1.0 / math.sqrt(2)]
        dot = sum(x * y for x, y in zip(a, b))
        assert math.isclose(cosine_similarity(a, b), dot, abs_tol=1e-6)

    def test_high_dimensional_vectors(self):
        """Fonctionne sur 384 dimensions (taille réelle des embeddings)."""
        a = [1.0] + [0.0] * 383
        b = [0.9] + [0.1] * 383
        result = cosine_similarity(a, b)
        assert -1.0 <= result <= 1.0
