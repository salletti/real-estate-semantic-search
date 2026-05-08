"""
LLM — Intent Merger (V4)
==========================

RÔLE
-----
Fusionne le `PropertyIntent` du rule parser avec le `LlmIntentResponse` validé.

Priorité :
    Rule parser > LLM sur les champs stricts
    LLM > Rule parser uniquement pour remplir les trous (champs None)

SÉCURITÉ DU MERGE
------------------
Si le rule parser a détecté city="Paris" et le LLM dit city="Lyon" :
→ "Paris" conservé. Le LLM n'overwrite JAMAIS un champ déjà renseigné.

Seul exception : semantic_terms → UNION (les deux contribuent).

RE-DÉDUCTION DE L'INTENT
--------------------------
Après le merge, l'intent peut avoir changé car de nouveaux champs sont apparus.
Règle : on ne met à jour l'intent QUE s'il était `unknown` avant le merge.

CRITIQUE — Sémantique pure ≠ property_search :
    Si le LLM ajoute uniquement semantic_terms (pas de champ structuré) :
    → intent reste `unknown`
    → le Query Engine utilisera le chemin "semantic_only"
    Ce comportement est VOULU : une requête sans structure = recherche sémantique pure.

    Si le LLM ajoute property_type ou city → intent = property_search ✓
"""

from app.entities.nlp.llm_intent_schema import LlmIntentResponse
from app.entities.nlp.intent_schema import IntentType, PropertyIntent, TransactionType


def merge_intents(rule: PropertyIntent, llm: LlmIntentResponse) -> PropertyIntent:
    """Fusionne le résultat du rule parser avec le résultat LLM validé.

    Le rule parser est la source de vérité. Le LLM ne remplit que les trous.

    Args:
        rule: PropertyIntent produit par le rule parser (fiable).
        llm: LlmIntentResponse validé par llm_validator (partiellement fiable).

    Returns:
        PropertyIntent fusionné.
    """
    merged = rule.model_copy(deep=True)

    # ── Champs STRICTS : rule wins, LLM remplit uniquement si None ───────────
    if merged.city is None and llm.city:
        merged.city = llm.city

    if merged.max_price is None and llm.max_price:
        merged.max_price = llm.max_price

    if merged.min_rooms is None and llm.min_rooms:
        merged.min_rooms = llm.min_rooms

    # ── Champs SOUPLES : LLM remplit si rule n'a pas détecté ─────────────────
    if merged.property_type is None and llm.property_type:
        merged.property_type = llm.property_type

    if merged.transaction_type is None and llm.transaction_type:
        merged.transaction_type = llm.transaction_type

    # ── Semantic terms : UNION (LLM enrichit sans dupliquer) ─────────────────
    existing = set(merged.semantic_terms)
    for term in llm.semantic_terms:
        if term not in existing:
            merged.semantic_terms.append(term)
            existing.add(term)

    # ── Re-déduction de l'intent (uniquement si était `unknown`) ─────────────
    if merged.intent == IntentType.unknown:
        _redéduce_intent(merged)

    return merged


def _redéduce_intent(merged: PropertyIntent) -> None:
    """Met à jour l'intent in-place après l'enrichissement LLM.

    Règle critique : les semantic_terms seuls ne promotivement PAS à property_search.
    Il faut au moins un champ structuré (city, property_type, max_price, min_rooms)
    ou un transaction_type explicite.
    """
    has_structural = any(
        f is not None
        for f in (merged.city, merged.property_type, merged.max_price, merged.min_rooms)
    )

    if merged.transaction_type == TransactionType.rental:
        merged.intent = IntentType.rental_search
    elif has_structural or merged.transaction_type == TransactionType.sale:
        merged.intent = IntentType.property_search
    # else: keep unknown — seuls semantic_terms enrichis, pas de signal structuré
