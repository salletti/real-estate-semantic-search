"""
NLP — Confidence Gate (V4)
============================

RÔLE DU GATE
--------------
Décide si le LLM doit être appelé pour enrichir le résultat du rule parser.

Analogie Symfony :
    Le Gate est un `VoterInterface` : il répond oui/non à la question
    "ce token mérite-t-il un traitement coûteux ?".

    class LlmUsageVoter implements VoterInterface {
        public function vote(TokenInterface $token, ...) {
            return $this->isLowConfidence($token) ? ACCESS_GRANTED : ACCESS_DENIED;
        }
    }

PHILOSOPHIE DU GATE
--------------------
Le LLM coûte du temps (latence réseau ~100-300ms) même sur Groq (free tier).
Le rule parser coûte ~0ms. Le Gate minimise les appels LLM en les réservant
aux requêtes où la valeur ajoutée justifie le coût.

Stratégie en deux phases :

    Phase 1 — "No LLM" (2 signaux forts) :
        Si la requête a DÉJÀ deux champs structurés, le rule parser a bien
        compris. Le LLM ne peut pas apporter grand-chose.
        Exemples :
            "appartement paris"           → city + property_type → False
            "maison sous 500k"            → property_type + max_price → ... (voir ci-dessous)

    Phase 2 — "Use LLM" (1 signal ou moins, ou typo probable) :
        Si un seul champ est reconnu, il reste ambiguïté (l'autre champ
        pourrait être une faute de frappe). Ou si la requête est floue.

DÉTECTION DE TYPO PROBABLE
----------------------------
`has_possible_typo(query)` détecte les tokens à distance Levenshtein = 2 des
keywords structurels. Distance 1 est déjà gérée par le rule parser V2.4.
Distance 2 = zone grise : le rule parser a raté, le LLM peut corriger.

Stop conditions :
    - tokens < 5 chars : trop courts pour être des typos de keywords structurels
    - filtre de longueur abs(len(token) - len(kw)) > 2 : coupe court les paires
      clairement incompatibles avant de lancer Levenshtein
"""

import re

from app.entities.nlp.fuzzy_matching import _levenshtein
from app.entities.nlp.intent_schema import IntentType, PropertyIntent

# Keywords structurels de référence pour la détection de typos.
# Ces mots sont les "cibles" que l'utilisateur essaie probablement de taper.
# Pas besoin de la liste complète : seuls les mots longs (≥ 5 chars) peuvent
# être confondus avec des fautes de frappe significatives.
_STRUCTURAL_TOKENS: frozenset[str] = frozenset({
    "appartement",
    "maison",
    "villa",
    "studio",
    "loft",
    "terrain",
    "commerce",
    "parking",
    "duplex",
    "penthouse",
    "pavillon",
    "maisonette",
    "residence",
})


def has_possible_typo(query: str) -> bool:
    """Détecte si la requête contient un token probablement mal orthographié.

    Heuristique V1 :
        Un token est "suspect" s'il est à distance Levenshtein = 2 d'un keyword
        structurel connu. Distance 1 est déjà gérée par le rule parser (V2.4).

    Exemples :
        "aprtement"  → distance 2 de "appartement"  → True  (LLM utile)
        "lumineux"   → distance >> 2 de tout keyword → False (terme sémantique)
        "villla"     → distance 1 de "villa"          → False (rule parser gère)
        "pavvillon"  → distance 2 de "pavillon"       → True  (LLM utile)

    Analogie PHP :
        similar_text() + seuil sur le score de correspondance.
        On fait mieux ici : distance de Levenshtein exacte.

    Args:
        query: Requête originale (non normalisée, la casse est ignorée).

    Returns:
        True si au moins un token est probablement une faute de niveau 2.
    """
    tokens = re.findall(r"\b\w+\b", query.lower())
    for token in tokens:
        if len(token) < 5:
            continue
        for kw in _STRUCTURAL_TOKENS:
            # Filtre rapide sur la différence de longueur
            if abs(len(token) - len(kw)) > 2:
                continue
            if _levenshtein(token, kw) == 2:
                return True
    return False


def should_use_llm(intent: PropertyIntent, query: str) -> tuple[bool, str]:
    """Décide si le LLM doit être invoqué pour enrichir le PropertyIntent.

    Returns:
        (use_llm: bool, reason: str)

    Logique en deux phases :

    PHASE 1 — SKIP LLM (2 signaux forts = confidence haute) :
        Si le rule parser a détecté 2 champs structurels différents, il a
        probablement bien compris la requête. Le LLM n'ajoute rien.

    PHASE 2 — USE LLM (ambiguïté détectée) :
        Un seul signal → l'autre champ est peut-être une faute non rattrapée.
        Requête longue / sémantiquement riche → LLM apporte de la valeur.
        Typo probable → LLM corrige là où le fuzzy parser V2.4 a échoué.

    Analogie Symfony :
        comme un VoterInterface avec ACCESS_DENIED (phase 1) > ACCESS_GRANTED
        (phase 2) > abstention (default False).
    """
    tokens = query.strip().split()

    # ── PHASE 1 : deux signaux forts → pas de LLM ────────────────────────────
    # city + property_type = la requête principale est bien comprise
    if intent.city and intent.property_type:
        return False, "city + property_type detected"

    # city + max_price = localisation + contrainte financière explicite
    if intent.city and intent.max_price:
        return False, "city + max_price detected"

    # property_type + transaction_type = nature du bien + type de transaction
    if intent.property_type and intent.transaction_type:
        return False, "property_type + transaction_type detected"

    # ── PHASE 2 : LLM utile ───────────────────────────────────────────────────

    # Typo probable (distance 2) → le rule parser a raté, le LLM peut corriger
    if has_possible_typo(query):
        return True, "possible typo detected (Levenshtein distance 2)"

    # Intent inconnu → aucun signal structurel détecté
    if intent.intent == IntentType.unknown:
        return True, "intent unknown — no structured signal"

    # Requête longue → probablement formulée de façon libre
    if len(tokens) > 12:
        return True, f"long query ({len(tokens)} tokens > 12)"

    # Beaucoup de termes sémantiques → la requête est riche et floue
    if len(intent.semantic_terms) > 4:
        return True, f"rich semantic query ({len(intent.semantic_terms)} terms > 4)"

    # Un seul signal structurel → l'autre champ est peut-être une typo
    if intent.city and not intent.property_type:
        return True, "city detected but no property_type — possible typo"

    if intent.property_type and not intent.city:
        return True, "property_type detected but no city — possible typo"

    if not intent.city and not intent.property_type:
        return True, "no city nor property_type detected"

    # ── Default : le rule parser a fait son travail ───────────────────────────
    return False, "sufficient structure"
