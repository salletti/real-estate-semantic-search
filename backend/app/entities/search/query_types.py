"""
Query Engine — Types
=====================

Ce module définit les types de décision du moteur de recherche :
- QueryStrategy   : quelle stratégie utiliser (SQL / Sémantique / Hybride / Nearby)
- QueryResolution : le résultat de la décision, avec son contexte
- SearchResult    : DTO interne portant un bien + son score de pertinence
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.adapters.gateways.db.models.property import Property


class QueryStrategy(str, Enum):
    sql_only = "sql_only"
    semantic_only = "semantic_only"
    hybrid = "hybrid"
    nearby = "nearby"


class QueryResolution(BaseModel):
    strategy: QueryStrategy
    has_structured_filters: bool
    has_semantic_terms: bool
    reason: str


@dataclass
class SearchResult:
    """DTO interne : bien immobilier enrichi de son score de pertinence.

    score    : None pour sql_only/nearby (tri arbitraire), float pour semantic/hybrid.
    strategy : stratégie qui a produit ce résultat (debug / transparence).
    """

    property: "Property"
    score: float | None
    strategy: QueryStrategy
