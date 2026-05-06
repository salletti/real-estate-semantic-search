"""
NLP — Fuzzy Matching V1 (Levenshtein distance)
================================================

CONCEPT : TROIS NIVEAUX DE MATCHING
-------------------------------------
Cette V2.4 introduit trois niveaux de tolérance, appliqués dans l'ordre :

    1. Exact match       : "villa"     == "villa"       → O(1) dict lookup
    2. Synonym mapping   : "pavillon"  →  "house"       → O(1) dict lookup (déjà étendu)
    3. Fuzzy matching    : "vilaa"     ≈  "villa"       → O(n×m) Levenshtein

Le fuzzy intervient uniquement quand les deux premiers ont échoué.

POURQUOI PAS ENCORE UN LLM ?
------------------------------
- Coût : chaque requête = tokens facturés (GPT-4 ≈ $0.01/requête en prod)
- Non-déterminisme : "apartement" peut donner "apartment" OU "appartement" selon
  la température, la session, la version du modèle
- Tests difficiles : `assert result == "apartment"` n'est plus garanti → on perd
  la confiance dans les tests de régression
- Debugging : un LLM ne peut pas expliquer POURQUOI il a retourné "house"

Avec Levenshtein V1 : résultat toujours identique, testable unitairement,
debuggable en moins de 5 minutes, gratuit à l'exécution.

ANALOGIE PHP
-------------
// Normalizer Symfony : transforme une valeur en canonical form
// Notre fuzzy = un "forgiving normalizer" qui tolère les fautes de frappe

    class TypoTolerantNormalizer implements NormalizerInterface {
        public function normalize($object, ...) {
            $closest = $this->levenshteinSearch($object->value, $this->validValues);
            return $closest ?? null;
        }
    }

IMPLÉMENTATION PURE PYTHON — PAS DE DÉPENDANCE EXTERNE
--------------------------------------------------------
La bibliothèque python-Levenshtein (C extension) serait plus rapide pour de
grandes listes, mais pour max_distance=1 sur ~20 keywords, le surcoût est
négligeable et l'absence de dépendance simplifie le Dockerfile.
"""


def _levenshtein(a: str, b: str) -> int:
    """Calcule la distance de Levenshtein entre deux chaînes.

    Algorithme DP standard, O(|a| × |b|) temps et O(|b|) espace.

    Distance = nombre minimal d'opérations élémentaires pour transformer a en b :
        - Insertion  : "vill"  → "villa"  (1 insertion)
        - Suppression: "villaa" → "villa"  (1 suppression)
        - Substitution: "villo" → "villa" (1 substitution)

    Analogie PHP :
        similar_text() mesure la similarité mais pas la distance de Levenshtein.
        levenshtein() existe en PHP natif — même algorithme, même complexité.
    """
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for ca in a:
        curr = [prev[0] + 1]
        for j, cb in enumerate(b):
            curr.append(min(
                prev[j + 1] + 1,       # suppression dans a
                curr[j] + 1,           # insertion dans a
                prev[j] + (ca != cb),  # substitution (0 si identiques)
            ))
        prev = curr
    return prev[-1]


def find_closest_keyword(
    token: str,
    candidates: set[str],
    max_distance: int = 1,
) -> str | None:
    """Trouve le candidat unique le plus proche du token, dans max_distance.

    Retourne :
    - Le candidat unique si exactement 1 candidat est à distance ≤ max_distance
    - None si 0 candidat (aucun match)
    - None si ≥ 2 candidats (ambiguïté — mieux vaut ne pas deviner)

    STOP CONDITIONS (intentionnelles) :
        len(token) <= 2 : "pa" ne doit jamais fuzzy-matcher "paris" ni "parking".
                          Les tokens très courts génèrent trop de faux positifs.
                          Exemples dangereux sans cette règle :
                            "la" → "loft"  (distance 1)
                            "ou" → "loue"  (distance 2... mais "lu" → "loue" distance 2)

    Pourquoi max_distance=1 ?
        Distance 1 couvre : 1 lettre manquante / en trop / transposée.
        "apartement" → "appartement" (1 'p' manquant)
        "vilaa"      → "villa"       (1 'a' en trop)
        Distance 2 génère des faux positifs sur les mots courts français :
            "pas" → "parking" ? "loft" ?  → trop risqué.

    Analogie PHP :
        // levenshtein() natif PHP — même sémantique
        $matches = array_filter($candidates, fn($c) => levenshtein($token, $c) <= 1);
        return count($matches) === 1 ? $matches[0] : null;

    Args:
        token: Token normalisé (minuscules, accents supprimés) à matcher.
        candidates: Ensemble des keywords valides (clés du dictionnaire).
        max_distance: Tolérance maximale (défaut : 1).

    Returns:
        Le keyword canonique si match unique, None sinon.
    """
    if len(token) <= 2:
        return None

    token_lower = token.lower()
    matches = [
        c for c in candidates
        if _levenshtein(token_lower, c.lower()) <= max_distance
    ]

    return matches[0] if len(matches) == 1 else None
