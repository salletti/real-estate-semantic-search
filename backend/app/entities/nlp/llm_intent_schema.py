"""
LLM — LlmIntentResponse DTO (V4)
==================================

POURQUOI UN DTO SÉPARÉ ?
--------------------------
`PropertyIntent` est le contrat de domaine — stable, validé, consommé par le
Query Engine. Il doit TOUJOURS être fiable.

`LlmIntentResponse` est une sortie brute du LLM — non fiable par nature.
Ne jamais l'utiliser directement sans validation.

Flow correct :
    LlmIntentResponse (non validé)
        → llm_validator.py (filtre hallucinations)
        → intent_merger.py (fusion avec le résultat rule-based)
        → PropertyIntent (validé, fiable)

Analogie DDD :
    LlmIntentResponse = ValueObject de la couche anti-corruption (ACL)
    PropertyIntent    = Aggregate de domaine

CHAMPS :
---------
- Champs STRICTS (city, max_price, min_rooms) :
  Le LLM ne DOIT PAS les inventer si absents de la requête.
  Le validator les rejette s'ils sont hallucinés.

- Champs SOUPLES (property_type, transaction_type, semantic_terms) :
  Le LLM PEUT les inférer (correction de fautes, synonymes, sémantique).

- confidence_score + explanation : métadonnées de debug.
"""

from pydantic import BaseModel, Field

from app.entities.nlp.intent_schema import PropertyType, TransactionType


class LlmIntentResponse(BaseModel):
    """DTO brut de la réponse LLM — non validé, non fiable.

    Doit impérativement passer par llm_validator avant usage.
    """

    # ── Champs STRICTS — ne jamais inventer ──────────────────────────────────
    city: str | None = None
    max_price: int | None = None
    min_rooms: int | None = None

    # ── Champs SOUPLES — correction / inférence autorisée ────────────────────
    property_type: PropertyType | None = None
    transaction_type: TransactionType | None = None
    semantic_terms: list[str] = Field(default_factory=list)

    # ── Métadonnées de debug ──────────────────────────────────────────────────
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    explanation: str = ""
