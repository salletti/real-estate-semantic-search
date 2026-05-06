"""
Qdrant Store V1
================

RÔLE
----
Factory de clients Qdrant et création de la collection 'properties'.

NAMING : qdrant_store.py et non qdrant_client.py
  → évite tout shadow de l'import `from qdrant_client import ...`
    (le package installé se nomme `qdrant_client`, ce fichier serait `app.adapters.gateways.vector_db.qdrant_store`)

ANALOGIE SYMFONY / PHP
-----------------------
Qdrant est à Elasticsearch ce qu'Elasticsearch est à MySQL :

    PostgreSQL  = données structurées (filtres exacts)         → SQL search V1
    Elasticsearch = recherche texte (full-text, fuzzy)
    Qdrant        = recherche par SENS (similarité vectorielle) → Semantic V2

La "collection" Qdrant correspond à un "index" Elasticsearch ou une "table" SQL.
Chaque document est un "point" avec :
    id      : int — le property.id de PostgreSQL (même ID, deux bases liées)
    vector  : list[float] — les 384 floats qui encodent le sens du bien
    payload : dict — métadonnées (city, type, price…) comme les "fields" Elasticsearch

DEUX CLIENTS
------------
QdrantClient (sync)       → pour les scripts d'indexation (pas d'event loop)
AsyncQdrantClient (async) → pour les services FastAPI (event loop active)
"""

from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.core.config import settings

VECTOR_SIZE = 384


def get_sync_client() -> QdrantClient:
    """Client synchrone — pour scripts et gestion de collection."""
    cfg = settings.vector_store
    if cfg.url:
        return QdrantClient(url=cfg.url, api_key=cfg.api_key)
    return QdrantClient(host=cfg.host, port=cfg.port)


def get_async_client() -> AsyncQdrantClient:
    """Client asynchrone — pour les services FastAPI.

    Utiliser comme context manager :
        async with get_async_client() as client:
            results = await client.search(...)
    """
    cfg = settings.vector_store
    if cfg.url:
        return AsyncQdrantClient(url=cfg.url, api_key=cfg.api_key)
    return AsyncQdrantClient(host=cfg.host, port=cfg.port)


def ensure_collection(client: QdrantClient) -> None:
    """Crée la collection 'properties' si elle n'existe pas encore.

    Idempotente — sans effet si la collection existe déjà.
    À appeler une fois au démarrage du script d'indexation.
    """
    if not client.collection_exists(settings.vector_store.collection_name):
        client.create_collection(
            collection_name=settings.vector_store.collection_name,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
