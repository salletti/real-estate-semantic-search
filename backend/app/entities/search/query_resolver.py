"""
Query Resolver V1
==================

Responsabilité unique : prendre un PropertyIntent et décider quelle
stratégie de recherche appliquer.

ANALOGIE SYMFONY / PHP
-----------------------
Ce module joue le rôle d'un Resolver dans Symfony — il n'exécute rien,
il détermine COMMENT le traitement doit se faire, puis délègue.

    // PHP — Resolver pattern
    class QueryResolver
    {
        public function resolve(SearchIntent $intent): QueryStrategy
        {
            if ($intent->hasSemanticTerms() && $intent->hasFilters()) {
                return new HybridStrategy();
            }
            // ...
        }
    }

Ici, on retourne un DTO de résolution plutôt qu'un objet stratégie,
car en V1 seul SQL est implémenté. Le query_executor (V2) recevra
cette résolution et instanciera la bonne stratégie.

RÈGLES V1
----------
Filtres structurés reconnus :
    city, property_type, max_price, min_rooms, mandate_type, transaction_type

Termes sémantiques :
    semantic_terms non vide

Décision :
    structured seulement  → sql_only
    sémantique seulement  → semantic_only
    les deux              → hybrid
    rien (vide)           → sql_only  (fallback safe)
"""

from app.entities.nlp.intent_schema import PropertyIntent
from app.entities.search.query_types import QueryResolution, QueryStrategy

def resolve_query(intent: PropertyIntent) -> QueryResolution:
    """Décide quelle stratégie de recherche utiliser pour un intent donné.

    Ne lève jamais d'exception — le fallback sql_only est toujours retourné
    pour un intent vide ou non reconnu.

    Args:
        intent: DTO extrait par le NLP parser.

    Returns:
        QueryResolution avec la stratégie choisie et son explication.
    """
    has_structured = intent.has_structured_filters()
    has_semantic = intent.has_semantic_terms()

    if intent.nearby_city and intent.search_radius_km:
        return QueryResolution(
            strategy=QueryStrategy.nearby,
            has_structured_filters=True,
            has_semantic_terms=has_semantic,
            reason="nearby_city + search_radius_km -> nearby",
        )

    if has_structured and has_semantic:
        return QueryResolution(
            strategy=QueryStrategy.hybrid,
            has_structured_filters=True,
            has_semantic_terms=True,
            reason="structured filters + semantic_terms → hybrid",
        )

    if has_semantic:
        return QueryResolution(
            strategy=QueryStrategy.semantic_only,
            has_structured_filters=False,
            has_semantic_terms=True,
            reason="semantic_terms only → semantic_only",
        )

    return QueryResolution(
        strategy=QueryStrategy.sql_only,
        has_structured_filters=has_structured,
        has_semantic_terms=False,
        reason="structured filters only → sql_only"
        if has_structured
        else "no filters detected → sql_only (safe fallback)",
    )
