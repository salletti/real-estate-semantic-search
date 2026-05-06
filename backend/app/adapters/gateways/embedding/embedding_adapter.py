from sentence_transformers import SentenceTransformer

from app.core.config import settings
from app.usecases.gateway.embedding_gateway import EmbeddingGateway


class EmbeddingAdapter(EmbeddingGateway):
    async def embed(self, text: str) -> list[float]:
        return embed_text(text)


VECTOR_SIZE = 384

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Charge le modèle au premier appel, le réutilise ensuite."""
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.embeddings.model_name)
    return _model


def embed_text(text: str) -> list[float]:
    """Génère un embedding pour un texte donné.

    Args:
        text: Texte à encoder — requête utilisateur ou description de bien.

    Returns:
        list[float] de longueur 384 — valeurs normalisées entre -1 et 1.

    Symfony équivalent :
        public function embed(string $text): array
        {
            return $this->model->encode($text, normalizeEmbeddings: true);
        }
    """
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()