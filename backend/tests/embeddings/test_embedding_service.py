"""
Tests — embedding_service.py
=============================

STRATÉGIE DE TEST
-----------------
embed_text() dépend de SentenceTransformer qui charge un modèle ~500MB.
On ne charge JAMAIS le vrai modèle en test — trop lent, inutile, et fragile
si HuggingFace Hub est inaccessible en CI.

Technique : monkeypatch `_model` directement dans le module.
`_get_model()` vérifie `if _model is None:`. Si on injecte un mock,
il est retourné directement sans toucher à SentenceTransformer.

ANALOGIE SYMFONY / PHPUNIT
---------------------------
// PHP — mock du service injecté
$model = $this->createMock(SentenceTransformer::class);
$model->method('encode')->willReturn(array_fill(0, 384, 0.1));
$service = new EmbeddingService($model);

# Python — pas d'injection constructeur, on patch le module-level state
monkeypatch.setattr("app.embeddings.embedding_service._model", mock_model)
result = embed_text("test")
"""

import numpy as np
import pytest
from unittest.mock import MagicMock

from app.adapters.gateways.embedding.embedding_adapter import embed_text
from app.adapters.gateways.vector_db.qdrant_store import VECTOR_SIZE


# =============================================================================
# Fixture — mock du modèle SentenceTransformer
# =============================================================================

@pytest.fixture
def mock_model(monkeypatch):
    """Injecte un faux modèle dans le module — aucun chargement HuggingFace."""
    fake_vector = np.array([0.1] * VECTOR_SIZE, dtype=np.float32)
    mock = MagicMock()
    mock.encode.return_value = fake_vector
    monkeypatch.setattr("app.adapters.gateways.embedding.embedding_adapter._model", mock)
    return mock


# =============================================================================
# Tests embed_text()
# =============================================================================

class TestEmbedText:
    def test_returns_list(self, mock_model):
        result = embed_text("bien immobilier lumineux")
        assert isinstance(result, list)

    def test_returns_list_of_floats(self, mock_model):
        result = embed_text("appartement Paris")
        assert all(isinstance(v, float) for v in result)

    def test_returns_correct_dimension(self, mock_model):
        """Doit retourner exactement VECTOR_SIZE (384) floats."""
        result = embed_text("lumineux terrasse vue mer")
        assert len(result) == VECTOR_SIZE

    def test_calls_encode_with_text(self, mock_model):
        """Le modèle doit recevoir le texte exact passé à embed_text()."""
        text = "maison avec jardin"
        embed_text(text)
        mock_model.encode.assert_called_once_with(text, normalize_embeddings=True)

    def test_calls_encode_with_normalize_true(self, mock_model):
        """normalize_embeddings=True est obligatoire pour cosine similarity correcte."""
        embed_text("test")
        _, kwargs = mock_model.encode.call_args
        assert kwargs["normalize_embeddings"] is True

    def test_model_reused_on_second_call(self, mock_model):
        """Le modèle singleton ne doit être chargé qu'une fois."""
        embed_text("premier appel")
        embed_text("deuxième appel")
        assert mock_model.encode.call_count == 2  # encode appelé 2x, pas _get_model()
