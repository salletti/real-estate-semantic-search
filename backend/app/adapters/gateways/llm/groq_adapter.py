"""
LLM — Intent Service (Groq via OpenAI SDK, V4)
================================================

RÔLE
-----
Appelle l'API Groq pour extraire un `LlmIntentResponse` depuis une requête.
Si l'appel échoue (timeout, API down, clé absente), retourne `None` →
le pipeline revient automatiquement au résultat du rule parser.

ANALOGIE SYMFONY
-----------------
Ce service est l'équivalent d'un `HttpClientInterface` Symfony injecté dans
un service métier :
    - Le client est lazy-loaded (initialisé au premier appel)
    - Les erreurs sont catchées et transformées en null → graceful degradation
    - Pas de couplage fort : le caller ne sait pas si le LLM a été appelé

GROQ POURQUOI ?
----------------
- API OpenAI-compatible → même SDK Python (openai>=1.35.0), zero friction
- Free tier généreux (14 400 req/jour sur llama-3.1-8b-instant)
- Latence ~100-200ms (inférence GPU dédiée, pas de file d'attente)
- JSON mode natif (`response_format={"type": "json_object"}`)
- `temperature=0` + `seed=42` → extraction déterministe, testable

ALTERNATIVES REJETÉES
-----------------------
| Option            | Raison du rejet                                     |
|---|---|
| Anthropic Claude  | SDK séparé, pas de JSON mode natif v1, coût plus élevé |
| OpenAI GPT-4o-mini | Payant dès le 1er token, pas de free tier          |
| Ollama local      | ~2Go RAM supplémentaire dans le Docker compose     |

LIMITES V1
-----------
- Numeric words ("cinq cent mille") → max_price=null (le validator vérifie les digits)
- Timeout 10s : si Groq est lent, on fallback sur le rule parser
- Pas de streaming : on attend la réponse complète (512 tokens max)
"""

import json
import logging

from openai import OpenAI

from app.core.config import settings
from app.entities.nlp.llm_intent_schema import LlmIntentResponse
from app.usecases.gateway.llm_gateway import LlmGateway

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.llm.api_key,
            base_url=settings.llm.base_url,
        )
    return _client


_SYSTEM_PROMPT = """
You are a French real estate search intent extractor.
Given a user query, extract structured information and return ONLY valid JSON.

JSON SCHEMA:
{
  "property_type": "apartment" | "house" | "villa" | "studio" | "loft" | "land" | "commercial" | "parking" | null,
  "city": string | null,
  "max_price": integer | null,
  "min_rooms": integer | null,
  "transaction_type": "sale" | "rental" | null,
  "semantic_terms": [string, ...],
  "confidence_score": float (0.0 to 1.0),
  "explanation": string
}

STRICT RULES — NEVER violate:
1. city: Include ONLY if a real French city name is explicitly present in the query.
   "vers lyon" → "Lyon". "maison familiale" → null. NEVER invent.
2. max_price: Include ONLY if a specific digit-based amount is explicit.
   "500k" → 500000. "300 000 euros" → 300000. "pas cher" → null. NEVER invent.
   LIMITATION: written numbers ("cinq cent mille") → null (digits only supported).
3. min_rooms: Include ONLY if an explicit number is stated. "3 pièces" → 3. NEVER invent.

SOFT RULES — inference allowed:
4. property_type: Fix typos ("aprtement" → "apartment"), translate synonyms
   ("baraque" → "house", "pavillon" → "house", "penthouse" → "apartment").
5. transaction_type: Infer from context ("à louer" → "rental", "à vendre" → "sale").
6. semantic_terms: Enrich from context.
   "pas trop cher" → ["budget"], "familial" → ["familial"], "lumineux" → ["lumineux"].
   Keep them short, lowercase, descriptive.

Respond with ONLY the JSON object. No markdown, no explanation outside JSON.
""".strip()


class GroqLlmAdapter(LlmGateway):
    def parse_intent(self, query: str) -> LlmIntentResponse | None:
        return parse_intent_with_llm(query)


def parse_intent_with_llm(query: str) -> LlmIntentResponse | None:
    """Extrait un LlmIntentResponse depuis Groq.

    Returns None si l'appel échoue (graceful degradation vers le rule parser).

    Args:
        query: Requête utilisateur originale (non normalisée).

    Returns:
        LlmIntentResponse si succès, None si erreur ou clé absente.
    """
    if not settings.llm.api_key:
        logger.debug("GROQ_API_KEY not set — skipping LLM call")
        return None

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=settings.llm.model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            response_format={"type": "json_object"},
            temperature=settings.llm.temperature,
            seed=settings.llm.seed,
            max_tokens=settings.llm.max_tokens,
            timeout=settings.llm.timeout_seconds,
        )

        raw = response.choices[0].message.content
        if not raw:
            logger.warning("LLM returned empty content")
            return None

        data: dict = json.loads(raw)

        for field in ("property_type", "city", "transaction_type"):
            if isinstance(data.get(field), str) and data[field].lower() in ("null", "none", ""):
                data[field] = None

        return LlmIntentResponse.model_validate(data)

    except Exception as exc:
        logger.warning("LLM parse failed (%s: %s)", type(exc).__name__, exc)
        return None
