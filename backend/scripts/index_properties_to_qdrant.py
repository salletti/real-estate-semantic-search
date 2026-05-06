"""
Script d'indexation — Properties → Qdrant
==========================================

RÔLE
----
Lire tous les biens et leurs descriptions depuis PostgreSQL,
générer un embedding pour chacun, et l'upsert dans Qdrant.

USAGE
-----
    docker compose exec backend python scripts/index_properties_to_qdrant.py

IDEMPOTENT — peut être rejoué sans créer de doublons.
L'upsert Qdrant écrase le point existant si l'ID est identique.

TEXTE SÉMANTIQUE CONSTRUIT PAR BIEN
-------------------------------------
    "{type} {city} {rooms_count} pièces {mandate_price}€. {description}"

Ce texte amalgame les données structurées (filtrables en SQL) et la description
libre (searchable sémantiquement). L'embedding capte le sens global du bien.

PAYLOAD QDRANT
--------------
Métadonnées stockées avec chaque point :
    property_id : int   — clé de jointure PostgreSQL (= Qdrant point id)
    city        : str
    type        : str
    price       : float
    description : str (tronqué à 300 chars pour alléger le stockage)

ANALOGIE SYMFONY / PHP
-----------------------
Ce script est l'équivalent d'une commande Symfony Console :

    class IndexPropertiesCommand extends Command
    {
        public function execute(InputInterface $in, OutputInterface $out): int
        {
            $properties = $this->em->getRepository(Property::class)->findAll();
            foreach ($properties as $p) {
                $text   = $this->buildText($p);
                $vector = $this->embeddingService->embed($text);
                $this->qdrant->upsert('properties', $p->getId(), $vector, [...payload]);
            }
            $out->writeln(sprintf('Indexed %d properties.', count($properties)));
            return Command::SUCCESS;
        }
    }
"""

import asyncio
import os
import sys

# Ensure backend root (/app) is in sys.path for local execution.
# Inside Docker, PYTHONPATH=/app covers this automatically.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.adapters.gateways.db.models.property import Property
from app.adapters.gateways.db.session import AsyncSessionLocal
from app.adapters.gateways.embedding.embedding_adapter import embed_text
from app.entities.embeddings.text_builder import build_semantic_text
from app.adapters.gateways.vector_db.qdrant_store import ensure_collection, get_sync_client
from app.core.config import settings
from qdrant_client.models import PointStruct


async def load_properties() -> list[Property]:
    """Charge tous les biens avec leurs descriptions depuis PostgreSQL.

    selectinload() → une seule requête supplémentaire pour toutes les descriptions.
    Évite le problème N+1 (1 requête par property.descriptions).

    Doctrine équivalent :
        $qb->leftJoin('p.descriptions', 'd')->addSelect('d');
    """
    async with AsyncSessionLocal() as session:
        stmt = select(Property).options(selectinload(Property.descriptions))
        result = await session.execute(stmt)
        return list(result.scalars().all())


async def main() -> None:
    print("=== Indexation Qdrant — Properties V1 ===\n")

    # ── Étape 1 : Préparer la collection Qdrant ────────────────────────────────
    sync_client = get_sync_client()
    ensure_collection(sync_client)
    print(f"✓ Collection '{settings.vector_store.collection_name}' prête (créée ou déjà existante)")

    # ── Étape 2 : Charger les properties depuis PostgreSQL ─────────────────────
    print("  Chargement des properties depuis PostgreSQL...")
    properties = await load_properties()
    print(f"✓ {len(properties)} properties chargées")

    if not properties:
        print("⚠  Aucune property trouvée — base de données vide ?")
        print("   Exécuter d'abord : python scripts/seed_database.py")
        return

    # ── Étape 3 : Générer embeddings et construire les points Qdrant ──────────
    print("  Génération des embeddings (premier run : téléchargement du modèle ~90MB)...")
    points: list[PointStruct] = []

    for i, prop in enumerate(properties, 1):
        text = build_semantic_text(prop)
        vector = embed_text(text)

        description_text = prop.descriptions[0].description if prop.descriptions else ""

        points.append(PointStruct(
            id=prop.id,
            vector=vector,
            payload={
                "property_id": prop.id,
                "city": prop.city,
                "type": prop.type,
                "price": float(prop.mandate_price or 0),
                "description": description_text[:300],
            },
        ))

        if i % 10 == 0 or i == len(properties):
            print(f"  [{i}/{len(properties)}] embeddings générés...")

    # ── Étape 4 : Upsert batch dans Qdrant ────────────────────────────────────
    # Upsert = indexer ou réindexer — idempotent.
    # Un seul appel batch est plus efficace que N appels individuels.
    sync_client.upsert(collection_name=settings.vector_store.collection_name, points=points)

    print(f"\n✓ {len(points)} properties indexées dans Qdrant '{settings.vector_store.collection_name}'")
    print("  Prêt pour la recherche sémantique !")
    print("\nTest rapide :")
    print('  curl "http://localhost:8000/properties/search?q=lumineux%20avec%20terrasse"')


if __name__ == "__main__":
    asyncio.run(main())
