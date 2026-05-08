"""
NLP — Intent Parser V1 (pédagogique, rule-based)
==================================================

Convertit une phrase en langage naturel en PropertyIntent (DTO structuré).

    Input  : "Maison à Paris sous 500k"
    Output : PropertyIntent(city="Paris", property_type=house, max_price=500000)


APPROCHE RULE-BASED — LES 4 ÉTAPES
------------------------------------
1. Normaliser le texte (minuscules + suppression des accents)
2. Appliquer des dictionnaires de mots-clés → type de bien, transaction, mandat
3. Appliquer des regex → prix, nombre de pièces
4. Scanner une liste de villes connues → city
5. Assembler dans un PropertyIntent Pydantic


LIMITES DE CETTE APPROCHE (intentionnelles pour V1)
-----------------------------------------------------
- Une seule ville possible : "Paris ou Lyon" → city=Paris (premier match)
- Pas de contexte : "rue de Lyon à Bordeaux" → city=Lyon (faux positif possible)
- Fautes d'orthographe non gérées : "aprtement" → property_type=None
- Pluriel : "exclusifs" non reconnu (dictionnaire contient "exclusif")
- Villes hors liste : "Rambouillet" → city=None

Ces limites seront adressées en V2 avec :
- list[LocationConstraint] + LogicalOperator pour le multi-ville
- Patterns géographiques ("zone de X", "près de X") pour le contexte
- Un LLM pour gérer les fautes, synonymes et ambiguïtés
"""

import re
import unicodedata

from app.entities.nlp.confidence_gate import should_use_llm
from app.entities.nlp.fuzzy_matching import find_closest_keyword
from app.entities.nlp.intent_schema import (
    IntentType,
    MandateType,
    PropertyIntent,
    PropertyType,
    TransactionType,
)

# =============================================================================
# DICTIONNAIRES DE MOTS-CLÉS
# =============================================================================
# Structure : mot_clé_français → valeur_enum_canonique
# Le parseur compare chaque token de la requête contre ces dictionnaires.

_PROPERTY_TYPE_KEYWORDS: dict[str, PropertyType] = {
    # ── Exact keywords (V1) ───────────────────────────────────────────────────
    "maison": PropertyType.house,
    "villa": PropertyType.villa,
    "appartement": PropertyType.apartment,
    "appart": PropertyType.apartment,
    "studio": PropertyType.studio,
    "loft": PropertyType.loft,
    "terrain": PropertyType.land,
    "commerce": PropertyType.commercial,
    "local": PropertyType.commercial,
    "boutique": PropertyType.commercial,
    "parking": PropertyType.parking,
    "garage": PropertyType.parking,
    "box": PropertyType.parking,
    # ── Synonymes enrichis (V2.4) ────────────────────────────────────────────
    "pavillon": PropertyType.house,       # périphrase courante : pavillon = maison individuelle
    "maisonette": PropertyType.house,     # variante orthographique de "maisonnette"
    "residence": PropertyType.house,      # approximation : "résidence" peut désigner un immeuble ;
                                          # on mappe house faute d'un type "résidence" dans le schéma V1
    "baraque": PropertyType.house,        # registre familier / argotique
    "penthouse": PropertyType.apartment,  # appartement de luxe en dernier étage
    "duplex": PropertyType.apartment,     # appartement sur deux niveaux
}

# Liste fermée de villes françaises reconnues par le parseur V1.
# Limite intentionnelle : une ville absente de cette liste ne sera pas détectée.
# V2 : remplacer par une requête GeoNames ou PostGIS pour ~36 000 communes.
_CITY_LIST: set[str] = {
    "paris", "lyon", "marseille", "bordeaux", "toulouse", "nice",
    "nantes", "strasbourg", "montpellier", "lille", "rennes",
    "grenoble", "toulon", "dijon", "angers", "nimes", "aix-en-provence",
    "reims", "le havre", "saint-etienne", "villeurbanne",
    "clermont-ferrand", "brest", "limoges", "tours", "amiens",
    "metz", "perpignan", "caen", "nancy",
}

_SALE_KEYWORDS: set[str] = {
    "acheter", "achat", "vente", "vendre", "acquérir", "acquisition",
    "achete", "acquerir", "a vendre",
}
_RENTAL_KEYWORDS: set[str] = {
    "louer", "location", "loyer", "locatif", "bail", "loue",
    "a louer", "en location",
}
MANDATE_SYNONYMS: dict[str, MandateType] = {
    "mandat exclusif": MandateType.exclusive,
    "exclusif":        MandateType.exclusive,
    "exclusivite":     MandateType.exclusive,
    "exclu":           MandateType.exclusive,
    "exclusive":       MandateType.exclusive,
    "simple":          MandateType.simple,
    "non-exclusif":    MandateType.simple,
    "non exclusif":    MandateType.simple,
}

_EXCLUSIVE_KEYWORDS: set[str] = {k for k, v in MANDATE_SYNONYMS.items() if v == MandateType.exclusive}
_SIMPLE_MANDATE_KEYWORDS: set[str] = {k for k, v in MANDATE_SYNONYMS.items() if v == MandateType.simple}

# Abréviations de type location reconnues uniquement en token exact.
# "loc" NE PEUT PAS être dans _RENTAL_KEYWORDS (substring) car "loc" ⊂ "local"
# → faux positif : "local commercial" serait détecté comme location.
_RENTAL_TOKEN_KEYWORDS: set[str] = {"loc"}

# Sous-ensembles mono-token pour le fuzzy fallback de _extract_transaction_type.
# Les phrases multi-mots ("a louer", "en location") ne sont jamais fuzzy-matchées —
# un token isolé ne peut pas correspondre à une phrase entière.
_SALE_KEYWORDS_SINGLE: frozenset[str] = frozenset(kw for kw in _SALE_KEYWORDS if " " not in kw)
_RENTAL_KEYWORDS_SINGLE: frozenset[str] = frozenset(kw for kw in _RENTAL_KEYWORDS if " " not in kw)

# Stopwords : mots structurels à ignorer dans les semantic_terms.
#
# Trois catégories — chacune est du bruit grammatical, jamais une description
# qualitative du bien :
#
#   1. Articles, pronoms, déterminants
#
#   2. Prépositions et conjonctions de liaison
#      "sans", "mais", "comme", "entre"… relient des idées mais ne décrivent pas
#      le bien lui-même.
#
#   3. Verbes et adverbes de recherche
#      "cherche", "veux", "très"… expriment l'intention, pas la propriété.
#
# Garder : "lumineux", "calme", "terrasse", "renove", "moderne", "standing",
#           "travaux", "jardin", "neuf", "standing"… — valeur sémantique réelle.
_STOPWORDS: set[str] = {
    # ── 1. Articles, pronoms, déterminants ────────────────────────────────────
    "a", "de", "du", "des", "le", "la", "les", "en", "un", "une",
    "au", "aux", "mon", "ma", "mes", "je",
    "tout", "tous", "toute", "toutes", "cette", "cet", "ces",
    "leur", "leurs", "meme",
    # ── 2. Prépositions et conjonctions ───────────────────────────────────────
    "pour", "avec", "sans", "et", "ou", "sous", "sur", "dans", "par",
    "mais", "donc", "comme", "aussi", "dont",
    "vers", "chez", "apres", "avant", "entre", "depuis",
    "lors", "selon", "parmi",
    # ── 3. Verbes et adverbes de recherche ────────────────────────────────────
    "cherche", "veux", "voudrais", "trouver",
    "moins", "plus", "max", "maxi", "maximum", "budget", "environ", "tres",
    "non",
    # ── 5. Unités temporelles ─────────────────────────────────────────────────
    "jour", "jours",
    # ── 4. Adjectifs génériques non spécifiques au domaine ────────────────────
    "beau", "belle", "grand", "grande", "petit", "petite",
}

# =============================================================================
# PATTERNS REGEX
# =============================================================================

# Prix avec préposition de contexte : "sous 500k", "moins de 400 000", "< 300k"
# Groupe 1 : valeur numérique (ex: "500", "400 000")
# Groupe 2 : "k" si présent — multiplicateur × 1000
_PRICE_CONTEXT_RE = re.compile(
    r"(?:sous|moins de|<|max(?:i(?:mum)?)?|jusqu.a|inferieur a|budget|de moins de)\s*"
    r"(\d[\d\s]*)\s*(k)?\s*(?:€|euros?|eur)?(?:\b|$)",
    re.IGNORECASE,
)

# Prix avec symbole € sans préposition : "500 000€", "350000€"
# Nécessite 4+ chiffres pour éviter "500€" (loyer, pas prix d'achat)
_PRICE_BARE_RE = re.compile(
    r"(\d[\d\s]{3,})\s*(?:€|euros?|eur)(?:\b|$)",
    re.IGNORECASE,
)

# Nombre de pièces / chambres
# Groupe 1 : digit depuis "T3" ou "F3"    → notation française type appartement
# Groupe 2 : digit depuis "3 pièces" ou "3 chambres" (après normalisation accents)
_ROOMS_RE = re.compile(
    r"\b[tf](\d)\b"
    r"|(\d+)\s*(?:pieces?|pièces?|chambres?|rooms?)",
    re.IGNORECASE,
)

# Tokens de format structurel — ne sont PAS des termes sémantiques
# Exemples : "500k" (prix abrégé), "t3"/"f4" (notation française de pièces)
_PRICE_FORMAT_RE = re.compile(r"^\d+[kK]$")        # 500k, 300K
_ROOM_FORMAT_RE = re.compile(r"^[tf]\d+$", re.IGNORECASE)  # t3, f4, T10

# =============================================================================
# PATTERNS DE PROXIMITÉ GÉOGRAPHIQUE
# =============================================================================
# Détectés sur le texte normalisé (sans accents, minuscules).
# "à côté de" → "a cote de", "près de" → "pres de", etc.
#
# Priorité : détecté AVANT l'extraction de ville exacte (_extract_city).
# Si nearby_city est set → city reste None (invariant XOR du PropertyIntent).

_NEARBY_PATTERNS: list[str] = [
    "a cote de",
    "proche de",
    "pres de",
    "autour de",
    "aux alentours de",
    "dans les environs de",
]

# Rayon explicite : "dans un rayon de 20km de Boulogne Billancourt"
# Groupe 1 : valeur numérique du rayon (ex: "20")
# Groupe 2 : texte après "de " → ville cible (ex: "Boulogne Billancourt")
_NEARBY_RADIUS_RE = re.compile(
    r"dans (?:un |le )?rayon de\s+(\d+)\s*km\s+(?:de\s+)?(.+)",
    re.IGNORECASE,
)

_DEFAULT_NEARBY_RADIUS_KM = 15

# Tokens qui signalent la fin du nom de ville et le début d'un filtre métier.
# "proche de Le Havre sous 400k" → stopper à "sous".
# "pres de Aix-en-Provence t3" → stopper à "t3".
_CITY_STOP_TOKENS: frozenset[str] = frozenset({
    "sous", "moins", "plus", "avec", "budget", "max", "maxi",
    "t1", "t2", "t3", "t4", "t5", "f1", "f2", "f3", "f4", "f5",
    "pour", "sans",
})


# Temporalité de publication
# "plus de 30 jours" / "depuis 30 jours" / "publié il y a plus de 30 jours"
TIME_PATTERNS: dict[str, re.Pattern[str]] = {
    "more_than_days": re.compile(
        r"(?:plus de|depuis|publie il y a plus de|publie depuis plus de)\s*(\d+)\s*jours?",
        re.IGNORECASE,
    ),
    "less_than_days": re.compile(
        r"moins de\s*(\d+)\s*jours?",
        re.IGNORECASE,
    ),
}

# Extraction de nom de conseiller : "de Marie Dupont", "de Jean Martin"
# Requiert ≥ 2 mots en Title Case après "de" pour éviter les faux positifs sur une ville seule.
# Travaille sur le texte ORIGINAL (non normalisé) pour préserver la casse.
AGENT_PATTERNS: re.Pattern[str] = re.compile(
    r"\bde\s+([A-ZÀÂÇÉÈÊËÎÏÔÙÛÜŸ][a-zàâçéèêëîïôùûüÿ]+"
    r"(?:\s+[A-ZÀÂÇÉÈÊËÎÏÔÙÛÜŸ][a-zàâçéèêëîïôùûüÿ]+)+)\b"
)

# =============================================================================
# EXPRESSIONS SÉMANTIQUES COMPOSÉES
# =============================================================================
# Certaines expressions immobilières portent un sens uniquement en groupe.
# "vue" seul est ambigu ; "vue mer" est une valeur distincte et précieuse.
#
# Structure : tuple de tokens filtrés → expression canonique.
# Les stopwords internes ("bord DE mer") sont absents de la clé car ils sont
# filtrés AVANT la recherche de compound. Le tuple ne contient que les tokens
# sémantiques qui subsistent après filtrage.
#
# Ordre d'itération : longest-match-first (trié à la construction de la liste
# triée interne) — pas d'ambiguïté pour les clés actuelles (toutes 2-tuples).
_COMPOUND_SEMANTIC_PATTERNS: dict[tuple[str, ...], str] = {
    # ── Vue et environnement ──────────────────────────────────────────────────
    ("vue", "mer"):             "vue mer",
    ("vue", "jardin"):          "vue jardin",
    ("vue", "montagne"):        "vue montagne",
    ("bord", "mer"):            "bord de mer",      # "de" filtré comme stopword
    # ── Proximité ─────────────────────────────────────────────────────────────
    ("proche", "gare"):         "proche gare",
    ("proche", "mer"):          "proche mer",
    ("proche", "metro"):        "proche metro",
    ("proche", "ecoles"):       "proche ecoles",
    ("proche", "commerces"):    "proche commerces",
    # ── Localisation / niveau ─────────────────────────────────────────────────
    ("centre", "ville"):        "centre ville",
    ("dernier", "etage"):       "dernier etage",
    ("rez", "chaussee"):        "rez de chaussee",  # "de" filtré comme stopword
    ("plain", "pied"):          "plain pied",
}


# =============================================================================
# FONCTIONS PRIVÉES — UNE PAR DOMAINE D'EXTRACTION
# =============================================================================
# Convention de nommage : _extract_X() → retourne le champ X ou None
# Chaque fonction est pure, sans état, testable indépendamment.
# En V2, chaque fonction pourra être remplacée par un appel LLM.

def _normalize(text: str) -> str:
    """Minuscules + suppression des accents.

    Pourquoi : uniformiser l'input avant comparaison aux dictionnaires.
    Sans ça : "Appartement" ≠ "appartement", "exclusivité" ≠ "exclusivite".
    """
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _tokenize(normalized: str) -> list[str]:
    """Découpe le texte normalisé en liste de tokens de mots.

    Centralise re.findall(r'\\b\\w+\\b') — point de changement unique (DRY).
    Si le pattern évolue (support des tirets, chiffres composés...), une seule ligne à modifier.
    `\\b\\w+\\b` gère les frontières de mots sans dépendre des espaces — ponctuation et apostrophes ignorées.

    Exemple :
        _tokenize("maison à paris")  → ["maison", "a", "paris"]
        _tokenize("T3 sous 500k€")   → ["T3", "sous", "500k"]

    Impact V2 : si on remplace par un tokeniseur NLP (spaCy, NLTK), seule cette
    fonction change — les appelants (_extract_property_type, etc.) sont inchangés.
    """
    return re.findall(r"\b\w+\b", normalized)


def _extract_transaction_type(normalized: str) -> TransactionType | None:
    """Détecte si la requête porte sur un achat ou une location.

    Flow V2.4 (trois niveaux, rental toujours testé en premier — plus spécifique) :
        1. Exact / substring match  : "louer", "location", "a louer", "acheter"…
        2. Token exact              : "loc" (abréviation — token uniquement, pas substring)
        3. Fuzzy fallback           : "achatt" ≈ "achat" (distance Levenshtein ≤ 1)

    SQL équivalent : WHERE transaction_type = 'sale' | 'rental'
    """
    tokens = set(_tokenize(normalized))

    # 1. Exact / substring match (comportement V1 inchangé)
    if any(kw in normalized for kw in _RENTAL_KEYWORDS):
        return TransactionType.rental
    if any(kw in tokens for kw in _RENTAL_TOKEN_KEYWORDS):
        return TransactionType.rental
    if any(kw in tokens or kw in normalized for kw in _SALE_KEYWORDS):
        return TransactionType.sale

    # 2. Fuzzy fallback — uniquement sur les keywords mono-token
    #    Rental avant sale (même priorité que le flow exact)
    for token in _tokenize(normalized):
        if find_closest_keyword(token, _RENTAL_KEYWORDS_SINGLE):
            return TransactionType.rental
        if find_closest_keyword(token, _SALE_KEYWORDS_SINGLE):
            return TransactionType.sale

    return None


def _extract_property_type(normalized: str) -> PropertyType | None:
    """Détecte le type de bien depuis les tokens du dictionnaire.

    Flow V2.4 (trois niveaux, premier match dans l'ordre de lecture) :
        1. Exact / synonym match : "villa", "pavillon", "duplex"…  → O(1) dict lookup
        2. Fuzzy match           : "vilaa" ≈ "villa" (Levenshtein ≤ 1)

    Stop conditions fuzzy (délégué à find_closest_keyword) :
        - tokens ≤ 2 caractères : jamais fuzzy-matchés

    Limite V1 conservée : "maison ou appartement" → house (premier trouvé).

    SQL équivalent : WHERE type = 'house' | 'apartment' | ...
    """
    _candidates = set(_PROPERTY_TYPE_KEYWORDS.keys())
    for token in _tokenize(normalized):
        # 1. Exact / synonym match
        if token in _PROPERTY_TYPE_KEYWORDS:
            return _PROPERTY_TYPE_KEYWORDS[token]
        # 2. Fuzzy fallback
        closest = find_closest_keyword(token, _candidates)
        if closest:
            return _PROPERTY_TYPE_KEYWORDS[closest]
    return None


def _extract_nearby_city(normalized: str) -> tuple[str | None, int | None]:
    """Détecte un pattern de proximité géographique et extrait la ville cible + le rayon.

    Gère les villes composées : "Le Havre", "Aix-en-Provence", "Boulogne Billancourt".
    S'arrête au premier stop-token de filtre métier ("sous", chiffre, "t3"…).

    Exemples :
        "maison pres de Rambouillet"             → ("Rambouillet", 15)
        "maison proche de Le Havre sous 400k"    → ("Le Havre", 15)
        "dans un rayon de 20km de Lyon"          → ("Lyon", 20)
        "maison a Paris"                          → (None, None)

    Returns:
        (nearby_city, radius_km) ou (None, None) si aucun pattern détecté.
    """
    def _extract_city_tokens(after: str) -> str | None:
        """Extrait les tokens de ville jusqu'au premier stop-token ou chiffre."""
        city_tokens: list[str] = []
        for tok in after.split():
            if tok in _CITY_STOP_TOKENS or tok[0].isdigit():
                break
            city_tokens.append(tok)
        if not city_tokens:
            return None
        return " ".join(city_tokens).title()

    # Cas 1 : rayon explicite — "dans un rayon de 20km de Boulogne Billancourt"
    m = _NEARBY_RADIUS_RE.search(normalized)
    if m:
        radius_km = int(m.group(1))
        city = _extract_city_tokens(m.group(2).strip())
        return city, radius_km

    # Cas 2 : prefix de proximité sans rayon — "proche de Le Havre"
    for prefix in _NEARBY_PATTERNS:
        if prefix in normalized:
            after = normalized.split(prefix, 1)[1].strip()
            city = _extract_city_tokens(after)
            if city:
                return city, _DEFAULT_NEARBY_RADIUS_KM

    return None, None


def _extract_city(normalized: str) -> str | None:
    """Détecte le nom de la ville par matching dans la liste connue.

    Retourne la ville en titre (ex: "paris" → "Paris", "le havre" → "Le Havre").

    Stratégie : collecte TOUS les matches avec leur position, retourne le premier
    dans l'ordre du texte — pas dans l'ordre d'itération du set.

    Pourquoi la position ? Un set Python est non-ordonné.
    Sans ce fix, "Paris ou Lyon" pouvait retourner Lyon si le set itérait Lyon en premier.

    Limite V1 conservée :
      - Liste fermée — ville absente → city=None
      - "rue de Lyon à Bordeaux" → city=Lyon (pas de compréhension contextuelle)
      - V2 : patterns géographiques ("à X", "zone de X") + GeoNames

    SQL équivalent : WHERE city = 'Paris'
    """
    best_pos: int | None = None
    best_city: str | None = None
    for city in _CITY_LIST:
        m = re.search(r"\b" + re.escape(city) + r"\b", normalized)
        if m:
            if best_pos is None or m.start() < best_pos:
                best_pos = m.start()
                best_city = city
    if best_city:
        return best_city.title()

    # Fuzzy fallback: tolère une petite faute (ex: "montpelier" -> "montpellier")
    # mais ignore les tokens de bruit (stopwords/temporalité) pour éviter
    # des faux positifs comme "jours" -> "tours".
    tokens = _tokenize(normalized)
    for token in tokens:
        if token in _STOPWORDS:
            continue
        closest = find_closest_keyword(token, _CITY_LIST)
        if closest:
            return closest.title()
    return None


def _extract_max_price(normalized: str) -> int | None:
    """Extrait le prix plafond depuis des patterns comme "sous 500k", "moins de 400 000".

    Logique de décodage :
        "sous 500k"    → groupe1="500", groupe2="k" → 500 × 1000 = 500 000
        "moins de 400 000" → groupe1="400 000"       → strip spaces → 400 000
        "500000€"      → bare pattern                → 500 000

    SQL équivalent : WHERE mandate_price < :max_price
    """
    m = _PRICE_CONTEXT_RE.search(normalized)
    if m:
        raw = m.group(1).strip().replace(" ", "").replace(".", "")
        try:
            value = int(raw)
        except ValueError:
            return None
        if m.group(2):  # suffixe "k" → multiplier par 1000
            value *= 1000
        return value

    m = _PRICE_BARE_RE.search(normalized)
    if m:
        raw = m.group(1).strip().replace(" ", "").replace(".", "")
        try:
            return int(raw)
        except ValueError:
            return None

    return None


def _extract_min_rooms(normalized: str) -> int | None:
    """Extrait le nombre minimum de pièces.

    Patterns reconnus : "T3", "F3", "3 pièces", "3 chambres", "3 rooms"

    SQL équivalent : WHERE rooms_count >= :min_rooms
    """
    m = _ROOMS_RE.search(normalized)
    if not m:
        return None
    raw = m.group(1) or m.group(2)  # groupe 1 = T3/F3, groupe 2 = "3 pièces"
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _extract_mandate_type(normalized: str) -> MandateType | None:
    """Détecte le type de mandat depuis MANDATE_SYNONYMS."""
    for keyword, mandate_type in MANDATE_SYNONYMS.items():
        if keyword in normalized:
            return mandate_type
    return None


def _extract_published_more_than_days(normalized: str) -> int | None:
    """Extrait le seuil 'publié il y a plus de N jours'.

    Patterns reconnus : "plus de 30 jours", "depuis 30 jours",
    "publie il y a plus de 30 jours", "publie depuis plus de 30 jours".

    SQL équivalent : WHERE published_at < NOW() - INTERVAL ':days days'
    """
    m = TIME_PATTERNS["more_than_days"].search(normalized)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


def _extract_published_less_than_days(normalized: str) -> int | None:
    """Extrait le seuil 'publié il y a moins de N jours'.

    Pattern reconnu : "moins de 7 jours".

    SQL équivalent : WHERE published_at > NOW() - INTERVAL ':days days'
    """
    m = TIME_PATTERNS["less_than_days"].search(normalized)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


def _extract_agent_name(query: str) -> str | None:
    """Extrait un nom de conseiller depuis la requête originale (non normalisée).

    Pattern reconnu : "de Marie Dupont", "de Jean Martin"
    Requiert ≥ 2 mots en Title Case après "de" — évite "de Paris" (une seule ville).

    Limite V1 : aucune désambiguïsation avec les noms de villes ou lieux.
    V2 LLM fallback : si le nom est ambigu (prénom seul, homonyme géographique),
    déléguer la décision au LLM via parse_intent_with_llm().
    """
    m = AGENT_PATTERNS.search(query)
    return m.group(1) if m else None


def _deduce_intent(
    transaction_type: TransactionType | None,
    normalized: str,
    city: str | None,
    property_type: PropertyType | None,
    max_price: int | None,
    min_rooms: int | None,
    published_more_than_days: int | None = None,
    published_less_than_days: int | None = None,
    agent_name: str | None = None,
    nearby_city: str | None = None,
) -> IntentType:
    """Déduit l'intent global depuis l'ensemble des signaux extraits.

    Règles de priorité (ordre décroissant) :
    1. rental_search  : transaction_type == rental
    2. mandate_search : mot "mandat" présent dans la requête
    3. property_search: au moins un champ métier reconnu (y compris nearby_city)
    4. unknown        : aucun signal reconnu
    """
    if transaction_type == TransactionType.rental:
        return IntentType.rental_search
    if "mandat" in normalized:
        return IntentType.mandate_search
    if any(field is not None for field in (
        city, nearby_city, property_type, max_price, min_rooms,
        published_more_than_days, published_less_than_days, agent_name,
    )):
        return IntentType.property_search
    if transaction_type == TransactionType.sale:
        return IntentType.property_search
    return IntentType.unknown


def _is_noise_token(token: str) -> bool:
    """Détecte si un token est du bruit structurel sans valeur sémantique.

    Filtre les tokens qui représentent des données structurées (prix, pièces,
    nombres purs) mais qui ne contribuent pas au sens qualitatif d'une requête.

    Exemples exclus :
        "500k", "300K"  → prix abrégé     (_PRICE_FORMAT_RE)
        "t3", "f4"      → notation pièces (len <= 2)
        "t10"           → variante longue  (_ROOM_FORMAT_RE)
        "500", "3"      → nombre pur       (isdigit)
        "a", "ok"       → token très court (len <= 2)

    Exemples conservés :
        "lumineux", "calme", "renove", "terrasse", "vue" — termes sémantiques
    """
    if len(token) <= 2:
        return True
    if token.isdigit():
        return True
    if _PRICE_FORMAT_RE.match(token):
        return True
    if _ROOM_FORMAT_RE.match(token):
        return True
    return False


def _extract_compound_semantic_terms(
    tokens: list[str],
) -> tuple[list[str], set[int]]:
    """Détecte les expressions sémantiques composées dans une liste de tokens filtrés.

    Reçoit les tokens APRÈS filtrage (bruit + stopwords + recognized supprimés).
    Les stopwords internes aux compounds ("bord DE mer") ont déjà disparu — seuls
    les mots sémantiques restent, ce qui rend ("bord", "mer") détectable.

    Algorithme : greedy left-to-right, longest-match-first.
    Un index consommé ne peut appartenir qu'à un seul compound.

    Args:
        tokens: Liste de tokens déjà filtrés (sans bruit ni stopwords).

    Returns:
        (compounds, consumed) où :
            compounds — expressions composées détectées, dans l'ordre du texte.
            consumed  — ensemble des indices de `tokens` absorbés par les compounds.
    """
    compounds: list[str] = []
    consumed: set[int] = set()

    # Trier par longueur décroissante : longest-match-first évite qu'un 2-tuple
    # consomme le début d'un 3-tuple potentiel (extensibilité future).
    sorted_patterns = sorted(
        _COMPOUND_SEMANTIC_PATTERNS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    for i in range(len(tokens)):
        if i in consumed:
            continue
        for pattern, label in sorted_patterns:
            n = len(pattern)
            if tuple(tokens[i : i + n]) == pattern:
                compounds.append(label)
                consumed.update(range(i, i + n))
                break  # un seul compound par position de départ

    return compounds, consumed


def _extract_semantic_terms(normalized: str, recognized: set[str]) -> list[str]:
    """Collecte les termes sémantiques utiles après élimination du bruit.

    Pipeline en trois étapes :
        1. Filtrage — supprime le bruit structurel, grammatical et les termes
           déjà catégorisés (ville, type de bien, mots-clés transaction…).
        2. Compound detection — identifie les expressions composées
           (ex: "vue mer", "proche gare") avant de traiter les tokens isolés.
        3. Fusion text-order — restitue les compounds ET les tokens simples
           dans l'ordre d'apparition original, sans double-comptage.

    La priorité aux compounds (étape 2) garantit que "centre ville" est émis
    comme une seule unité plutôt que deux tokens séparés "centre" + "ville".
    L'ordre texte (étape 3) préserve la cohérence avec la requête originale :
        "studio moderne centre ville" → ["moderne", "centre ville"]
        et non ["centre ville", "moderne"].
    """
    # ── Étape 1 : filtrage ─────────────────────────────────────────────────────
    filtered = [
        token for token in _tokenize(normalized)
        if not _is_noise_token(token)
        and token not in _STOPWORDS
        and token not in recognized
    ]

    # ── Étape 2 : détection des expressions composées ─────────────────────────
    compounds, consumed = _extract_compound_semantic_terms(filtered)

    # ── Étape 3 : fusion dans l'ordre texte ───────────────────────────────────
    # On itère filtered une dernière fois. Pour chaque index :
    #   • non consommé         → token simple, on l'émet directement
    #   • consommé + premier   → début d'un compound, on dépile `compounds`
    #   • consommé + intérieur → token absorbé, on saute
    compound_iter = iter(compounds)
    terms: list[str] = []
    for i, token in enumerate(filtered):
        if i not in consumed:
            terms.append(token)
        elif i == 0 or (i - 1) not in consumed:
            # Premier index consommé d'une séquence → start d'un compound
            terms.append(next(compound_iter))
        # else: token intérieur/final d'un compound déjà émis → on saute

    return list(dict.fromkeys(terms))  # déduplique en préservant l'ordre


# =============================================================================
# POINT D'ENTRÉE PUBLIC
# =============================================================================

def parse_intent(query: str) -> PropertyIntent:
    """Analyse une requête en langage naturel et retourne un PropertyIntent.

    Point d'entrée unique du module.
    En V2, cette signature restera identique — seules les implémentations
    internes (_extract_*) seront remplacées par des appels au Claude API.

    Args:
        query: Requête utilisateur (ex: "Maison à Paris sous 500k").

    Returns:
        PropertyIntent avec les champs extraits. Champs non reconnus = None.

    Exemples:
        >>> parse_intent("Maison à Paris sous 500k").model_dump()
        {'intent': 'property_search', 'city': 'Paris', 'property_type': 'house',
         'max_price': 500000, 'min_rooms': None, 'mandate_type': None,
         'transaction_type': None, 'semantic_terms': []}

        >>> parse_intent("Louer studio Bordeaux").model_dump()
        {'intent': 'rental_search', 'city': 'Bordeaux', 'property_type': 'studio',
         'max_price': None, 'min_rooms': None, 'mandate_type': None,
         'transaction_type': 'rental', 'semantic_terms': []}

        >>> parse_intent("bonjour").model_dump()
        {'intent': 'unknown', 'city': None, 'property_type': None,
         'max_price': None, 'min_rooms': None, 'mandate_type': None,
         'transaction_type': None, 'semantic_terms': ['bonjour']}
    """
    # Étape 1 — Normalisation : minuscules + suppression accents
    # Sans ça, "Maison" ≠ "maison" et "exclusivité" ≠ "exclusivite"
    query_normalized = _normalize(query)

    # Étape 2a — Proximité géographique (priorité haute — avant _extract_city)
    # "à côté de Rambouillet" → nearby_city="Rambouillet", city reste None (invariant XOR)
    nearby_city, search_radius_km = _extract_nearby_city(query_normalized)

    # Étape 2b — Extraction de chaque champ de façon indépendante
    # Chaque fonction est pure — ordre sans importance entre elles
    transaction_type         = _extract_transaction_type(query_normalized)
    property_type            = _extract_property_type(query_normalized)
    city                     = None if nearby_city else _extract_city(query_normalized)
    max_price                = _extract_max_price(query_normalized)
    min_rooms                = _extract_min_rooms(query_normalized)
    mandate_type             = _extract_mandate_type(query_normalized)
    published_more_than_days = _extract_published_more_than_days(query_normalized)
    published_less_than_days = _extract_published_less_than_days(query_normalized)
    agent_name               = _extract_agent_name(query)  # texte original : casse préservée

    # Étape 3 — Intent global : dépend des extractions précédentes
    intent = _deduce_intent(
        transaction_type, query_normalized, city, property_type, max_price, min_rooms,
        published_more_than_days, published_less_than_days, agent_name,
        nearby_city=nearby_city,
    )

    # Étape 4 — Termes résiduels (tokens non catégorisés)
    recognized: set[str] = set()
    if city:
        recognized.update(city.lower().split())
    if nearby_city:
        # Les tokens du nom de ville voisine ne sont pas des termes sémantiques
        recognized.update(nearby_city.lower().split())
    if property_type:
        recognized.update(k for k, v in _PROPERTY_TYPE_KEYWORDS.items() if v == property_type)
    if agent_name:
        recognized.update(agent_name.lower().split())
    recognized |= _SALE_KEYWORDS | _RENTAL_KEYWORDS | _EXCLUSIVE_KEYWORDS | _SIMPLE_MANDATE_KEYWORDS
    semantic_terms = _extract_semantic_terms(query_normalized, recognized)

    # Étape 5 — Assemblage et validation du PropertyIntent par Pydantic
    return PropertyIntent(
        intent=intent,
        city=city,
        nearby_city=nearby_city,
        search_radius_km=search_radius_km,
        property_type=property_type,
        max_price=max_price,
        min_rooms=min_rooms,
        mandate_type=mandate_type,
        transaction_type=transaction_type,
        published_more_than_days=published_more_than_days,
        published_less_than_days=published_less_than_days,
        agent_name=agent_name,
        semantic_terms=semantic_terms,
    )


# =============================================================================
# PARSE INTENT V4 — Gated LLM Hybrid Parser
# =============================================================================

# Imports LLM ici (pas en tête de module) pour éviter d'alourdir le boot du
# module quand seul parse_intent() V2.4 est utilisé.
# Mocking path pour les tests : "app.nlp.intent_parser.parse_intent_with_llm"
from app.adapters.gateways.llm.groq_adapter import parse_intent_with_llm  # noqa: E402
from app.entities.nlp.llm_validator import validate_llm_response  # noqa: E402
from app.entities.nlp.intent_merger import merge_intents  # noqa: E402


def parse_intent_using_llm(query: str) -> PropertyIntent:
    """Parser hybride V4 : Rule-based + LLM gated.

    Flow :
        1. parse_intent(query)          → rule intent (toujours)
        2. should_use_llm(intent, query) → bool (gate)
        3. Si False → retourne le rule intent (0 latence LLM)
        4. Si True  → appelle Groq, valide, merge
        5. Si LLM échoue → retourne le rule intent (graceful degradation)

    Backward compatibility :
        parse_intent() V2.4 est INCHANGÉ — cette fonction est additive.
        Activée via USE_LLM=true dans .env (settings.use_llm).

    Args:
        query: Requête utilisateur (ex: "aprtement familial vers lyon").

    Returns:
        PropertyIntent — enrichi par le LLM si nécessaire, ou rule intent pur.
    """
    # Étape 1 : rule parser (toujours, synchrone, ~0ms)
    rule_intent = parse_intent(query)

    # Étape 2 : gate — vaut-il la peine d'appeler le LLM ?
    use_llm, _reason = should_use_llm(rule_intent, query)
    if not use_llm:
        return rule_intent

    # Étape 3 : LLM (Groq, synchrone, ~100-300ms)
    llm_response = parse_intent_with_llm(query)
    if llm_response is None:
        return rule_intent  # graceful degradation

    # Étape 4 : validation anti-hallucination
    validated = validate_llm_response(llm_response, query)

    # Étape 5 : fusion (rule wins on strict fields, LLM fills gaps)
    return merge_intents(rule_intent, validated).model_copy(update={"llm_used": True})
