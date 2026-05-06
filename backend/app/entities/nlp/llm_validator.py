"""
LLM — Validator (Anti-hallucination, V4)
==========================================

RÔLE
-----
Nettoie la sortie brute du LLM en rejetant les champs "inventés" non fondés
sur la requête originale.

ANALOGIE SYMFONY
-----------------
Ce validator est l'équivalent d'une `ConstraintValidator` Symfony :

    class NoInventedPriceValidator extends ConstraintValidator {
        public function validate($value, Constraint $constraint) {
            if ($value->maxPrice && !$this->hasDigitInQuery($constraint->query)) {
                $this->context->addViolation('Prix inventé — absent de la requête');
            }
        }
    }

CHAMPS STRICTS vs CHAMPS SOUPLES
----------------------------------
Ce validator ne touche QUE les champs STRICTS :

    STRICTS (rejetés si non fondés) :
        max_price  → doit avoir un chiffre dans la requête
        min_rooms  → doit avoir un chiffre dans la requête
        city       → doit avoir un mot de la ville dans la requête

    SOUPLES (jamais rejetés ici) :
        property_type   → correction de typo / synonyme : toujours gardé
        transaction_type → inférence de contexte : toujours gardé
        semantic_terms  → enrichissement sémantique : toujours gardé

LIMITE V1 DOCUMENTÉE
---------------------
Validation prix basée sur les CHIFFRES uniquement.
"moins de cinq cent mille" → aucun chiffre → max_price rejeté même si correct.
Cas non supporté en V1. À améliorer en V2 avec NLP des nombres écrits.

VALIDATION VILLE
-----------------
Le validator normalise les accents (unicodedata, stdlib) avant de chercher
le nom de la ville dans la requête. Ceci permet :
    "vers lyon" → "lyon" dans la requête normalisée → Lyon accepté ✓
    "appartement familial" → "paris" absent → Paris rejeté ✓
    "près d'aix" → "aix" dans "pres d'aix" normalisé → Aix accepté ✓
"""

import re
import unicodedata

from app.entities.nlp.llm_intent_schema import LlmIntentResponse

_DIGIT_RE = re.compile(r"\d")


def _strip_accents(text: str) -> str:
    """Supprime les accents via NFKD decomposition (stdlib, pas de dép externe)."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def validate_llm_response(
    llm: LlmIntentResponse,
    original_query: str,
) -> LlmIntentResponse:
    """Valide et nettoie la sortie LLM.

    Rejet des champs stricts hallucinés. Préservation des champs souples.

    Analogie DDD :
        Ce validator est la "couche anti-corruption" (ACL) entre le bounded
        context LLM (non fiable) et le bounded context Domain (fiable).

    Args:
        llm: Réponse brute du LLM (non fiable).
        original_query: Requête originale (non normalisée) — source de vérité.

    Returns:
        LlmIntentResponse nettoyé. Les champs invalides sont mis à None.
    """
    validated = llm.model_copy(deep=True)
    query_lower = _strip_accents(original_query.lower())

    # ── Validation max_price : exige au moins un chiffre dans la requête ──────
    if validated.max_price is not None:
        if not _DIGIT_RE.search(original_query):
            validated.max_price = None

    # ── Validation min_rooms : même logique que max_price ─────────────────────
    if validated.min_rooms is not None:
        if not _DIGIT_RE.search(original_query):
            validated.min_rooms = None

    # ── Validation city : au moins un mot de la ville dans la requête ─────────
    if validated.city is not None:
        city_normalized = _strip_accents(validated.city.lower()).replace("-", " ")
        city_words = [w for w in city_normalized.split() if len(w) > 2]
        if not city_words or not any(w in query_lower for w in city_words):
            validated.city = None

    return validated
