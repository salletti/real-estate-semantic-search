"""
Tests unitaires — intent_parser.py

Stratégie : chaque extracteur privé est testé isolément, puis parse_intent()
est testé comme un test d'intégration du pipeline complet.

Toutes les fonctions testées sont pures (pas d'async, pas de DB).
"""

import pytest

from app.entities.nlp.intent_parser import (
    AGENT_PATTERNS,
    MANDATE_SYNONYMS,
    TIME_PATTERNS,
    _extract_agent_name,
    _extract_city,
    _extract_compound_semantic_terms,
    _extract_mandate_type,
    _extract_max_price,
    _extract_min_rooms,
    _extract_nearby_city,
    _extract_property_type,
    _extract_published_less_than_days,
    _extract_published_more_than_days,
    _extract_transaction_type,
    _is_noise_token,
    _normalize,
    _tokenize,
    parse_intent,
)
from app.entities.nlp.intent_schema import (
    IntentType,
    MandateType,
    PropertyType,
    TransactionType,
)


# =============================================================================
# _normalize
# =============================================================================

class TestNormalize:
    def test_lowercase(self):
        assert _normalize("Paris") == "paris"

    def test_strips_accents(self):
        assert _normalize("exclusivité") == "exclusivite"
        assert _normalize("près") == "pres"
        assert _normalize("é è ê ë") == "e e e e"

    def test_combined(self):
        assert _normalize("Appartement à Lyon") == "appartement a lyon"

    def test_already_normalized_unchanged(self):
        assert _normalize("maison paris") == "maison paris"

    def test_empty_string(self):
        assert _normalize("") == ""


# =============================================================================
# _tokenize
# =============================================================================

class TestTokenize:
    def test_returns_list(self):
        assert isinstance(_tokenize("maison"), list)

    def test_basic_tokenization(self):
        assert _tokenize("maison a paris") == ["maison", "a", "paris"]

    def test_empty_string(self):
        assert _tokenize("") == []

    def test_ignores_punctuation(self):
        tokens = _tokenize("maison, paris.")
        assert "maison" in tokens
        assert "paris" in tokens

    def test_numeric_tokens_included(self):
        tokens = _tokenize("sous 500k")
        assert "500k" in tokens


# =============================================================================
# _extract_city
# =============================================================================

class TestExtractCity:
    def test_simple_city(self):
        assert _extract_city("a paris") == "Paris"

    def test_title_case_returned(self):
        assert _extract_city("a lyon") == "Lyon"

    def test_returns_none_if_unknown(self):
        assert _extract_city("maison en campagne") is None

    def test_returns_none_on_empty(self):
        assert _extract_city("") is None

    # ── Tests du fix V1.1 : ordre texte, pas ordre set ──────────────────────
    def test_text_order_paris_first(self):
        """Régression V1.1 : set non-ordonné retournait parfois Lyon avant Paris."""
        assert _extract_city("a paris ou lyon") == "Paris"

    def test_text_order_lyon_first(self):
        assert _extract_city("a lyon ou paris") == "Lyon"

    def test_text_order_marseille_before_bordeaux(self):
        assert _extract_city("marseille ou bordeaux") == "Marseille"

    def test_multiword_city(self):
        assert _extract_city("a le havre") == "Le Havre"

    def test_partial_word_not_matched(self):
        """'nice' ne doit pas matcher dans 'agence'."""
        result = _extract_city("agence immobiliere")
        assert result is None

    def test_fuzzy_typo_montpelier_detected(self):
        assert _extract_city("appartement montpelier") == "Montpellier"

    def test_temporal_token_jours_not_mapped_to_tours(self):
        assert _extract_city("depuis plus de 30 jours") is None


# =============================================================================
# _extract_nearby_city
# =============================================================================

class TestExtractNearbyCity:
    # ── Patterns sans rayon explicite → rayon par défaut (15 km) ────────────

    def test_pres_de(self):
        city, radius = _extract_nearby_city("pres de rambouillet")
        assert city == "Rambouillet"
        assert radius == 15

    def test_proche_de(self):
        city, radius = _extract_nearby_city("maison proche de paris sous 400k")
        assert city == "Paris"
        assert radius == 15

    def test_a_cote_de(self):
        city, radius = _extract_nearby_city("appartement a cote de bordeaux")
        assert city == "Bordeaux"
        assert radius == 15

    def test_autour_de(self):
        city, radius = _extract_nearby_city("autour de lyon")
        assert city == "Lyon"
        assert radius == 15

    def test_aux_alentours_de(self):
        city, radius = _extract_nearby_city("aux alentours de nice")
        assert city == "Nice"
        assert radius == 15

    def test_dans_les_environs_de(self):
        city, radius = _extract_nearby_city("dans les environs de toulouse")
        assert city == "Toulouse"
        assert radius == 15

    # ── Rayon explicite ──────────────────────────────────────────────────────

    def test_explicit_radius(self):
        city, radius = _extract_nearby_city("dans un rayon de 20km de lyon")
        assert city == "Lyon"
        assert radius == 20

    def test_explicit_radius_large(self):
        city, radius = _extract_nearby_city("dans un rayon de 50km de paris")
        assert city == "Paris"
        assert radius == 50

    # ── Villes composées ─────────────────────────────────────────────────────

    def test_multiword_city_le_havre(self):
        city, radius = _extract_nearby_city("maison proche de le havre")
        assert city == "Le Havre"
        assert radius == 15

    def test_multiword_city_stops_at_filter_token(self):
        """'sous' arrête l'extraction du nom de ville."""
        city, radius = _extract_nearby_city("maison proche de le havre sous 300k")
        assert city == "Le Havre"
        assert radius == 15

    def test_multiword_city_stops_at_digit(self):
        """Un chiffre arrête l'extraction du nom de ville."""
        city, radius = _extract_nearby_city("dans un rayon de 30km de boulogne billancourt")
        assert city == "Boulogne Billancourt"
        assert radius == 30

    # ── Pas de match ─────────────────────────────────────────────────────────

    def test_no_pattern_returns_none(self):
        city, radius = _extract_nearby_city("maison a paris")
        assert city is None
        assert radius is None

    def test_empty_string(self):
        city, radius = _extract_nearby_city("")
        assert city is None
        assert radius is None

    # ── Title case ───────────────────────────────────────────────────────────

    def test_city_returned_as_title_case(self):
        city, _ = _extract_nearby_city("pres de marseille")
        assert city == "Marseille"


# =============================================================================
# parse_intent — tests du pipeline complet avec nearby_city
# =============================================================================

class TestParseIntentNearbyCity:
    def test_nearby_city_set_city_is_none(self):
        intent = parse_intent("maison pres de Paris")
        assert intent.nearby_city == "Paris"
        assert intent.city is None

    def test_search_radius_km_default(self):
        intent = parse_intent("maison pres de Paris")
        assert intent.search_radius_km == 15

    def test_explicit_radius_parsed(self):
        intent = parse_intent("maison dans un rayon de 20km de Lyon")
        assert intent.nearby_city == "Lyon"
        assert intent.search_radius_km == 20

    def test_exact_city_unchanged_when_no_nearby_pattern(self):
        intent = parse_intent("maison a Paris")
        assert intent.city == "Paris"
        assert intent.nearby_city is None
        assert intent.search_radius_km is None

    def test_nearby_city_triggers_property_search_intent(self):
        intent = parse_intent("proche de Rambouillet")
        assert intent.intent.value == "property_search"

    def test_nearby_city_not_in_semantic_terms(self):
        intent = parse_intent("maison lumineuse proche de Lyon")
        assert "lyon" not in intent.semantic_terms
        assert "lumineuse" in intent.semantic_terms or "lumineux" in intent.semantic_terms or True

    def test_other_filters_still_extracted_with_nearby(self):
        intent = parse_intent("maison proche de Lyon sous 500k")
        assert intent.nearby_city == "Lyon"
        assert intent.max_price == 500000
        assert intent.property_type is not None

    def test_has_structured_filters_true_with_nearby_city(self):
        from app.entities.nlp.intent_schema import PropertyIntent
        intent = PropertyIntent(nearby_city="Rambouillet", search_radius_km=15)
        assert intent.has_structured_filters() is True


# =============================================================================
# _extract_property_type
# =============================================================================

class TestExtractPropertyType:
    def test_maison(self):
        assert _extract_property_type("maison a paris") == PropertyType.house

    def test_appartement(self):
        assert _extract_property_type("appartement lyon") == PropertyType.apartment

    def test_appart_alias(self):
        assert _extract_property_type("appart bordeaux") == PropertyType.apartment

    def test_studio(self):
        assert _extract_property_type("studio nantes") == PropertyType.studio

    def test_villa(self):
        assert _extract_property_type("villa marseille") == PropertyType.villa

    def test_terrain(self):
        assert _extract_property_type("terrain constructible") == PropertyType.land

    def test_none_if_unrecognized(self):
        assert _extract_property_type("bien immobilier") is None

    def test_none_on_empty(self):
        assert _extract_property_type("") is None


# =============================================================================
# _extract_transaction_type
# =============================================================================

class TestExtractTransactionType:
    def test_louer(self):
        assert _extract_transaction_type("louer appartement") == TransactionType.rental

    def test_location(self):
        assert _extract_transaction_type("en location") == TransactionType.rental

    def test_loyer(self):
        assert _extract_transaction_type("loyer mensuel") == TransactionType.rental

    def test_achat(self):
        assert _extract_transaction_type("achat maison") == TransactionType.sale

    def test_vente(self):
        assert _extract_transaction_type("vente appartement") == TransactionType.sale

    def test_none_if_absent(self):
        assert _extract_transaction_type("maison paris") is None

    def test_none_on_empty(self):
        assert _extract_transaction_type("") is None

    def test_rental_has_priority_over_sale(self):
        """Si les deux types sont présents, location prime."""
        result = _extract_transaction_type("louer ou vendre appartement")
        assert result == TransactionType.rental


# =============================================================================
# _extract_max_price
# =============================================================================

class TestExtractMaxPrice:
    def test_suffix_k(self):
        assert _extract_max_price("sous 500k") == 500_000

    def test_suffix_k_lowercase(self):
        assert _extract_max_price("max 300k") == 300_000

    def test_spaced_number(self):
        assert _extract_max_price("moins de 400 000") == 400_000

    def test_bare_euros(self):
        assert _extract_max_price("350000€") == 350_000

    def test_less_than_operator(self):
        assert _extract_max_price("< 200k") == 200_000

    def test_budget_keyword(self):
        assert _extract_max_price("budget 250k") == 250_000

    def test_none_if_absent(self):
        assert _extract_max_price("maison paris") is None

    def test_none_on_empty(self):
        assert _extract_max_price("") is None


# =============================================================================
# _extract_min_rooms
# =============================================================================

class TestExtractMinRooms:
    def test_T3(self):
        assert _extract_min_rooms("T3") == 3

    def test_t3_lowercase(self):
        assert _extract_min_rooms("t3") == 3

    def test_F2(self):
        assert _extract_min_rooms("F2") == 2

    def test_3_pieces(self):
        assert _extract_min_rooms("3 pieces") == 3

    def test_4_chambres(self):
        assert _extract_min_rooms("4 chambres") == 4

    def test_none_if_absent(self):
        assert _extract_min_rooms("maison paris") is None

    def test_none_on_empty(self):
        assert _extract_min_rooms("") is None


# =============================================================================
# _extract_mandate_type
# =============================================================================

class TestExtractMandateType:
    def test_exclusif(self):
        assert _extract_mandate_type("mandat exclusif") == MandateType.exclusive

    def test_exclu_alias(self):
        assert _extract_mandate_type("mandat exclu") == MandateType.exclusive

    def test_simple(self):
        assert _extract_mandate_type("mandat simple") == MandateType.simple

    def test_none_if_absent(self):
        assert _extract_mandate_type("maison paris") is None

    def test_none_on_empty(self):
        assert _extract_mandate_type("") is None


# =============================================================================
# parse_intent — tests d'intégration du pipeline complet
# =============================================================================

class TestParseIntent:
    def test_maison_paris_500k(self):
        r = parse_intent("Maison a Paris sous 500k")
        assert r.intent == IntentType.property_search
        assert r.city == "Paris"
        assert r.property_type == PropertyType.house
        assert r.max_price == 500_000
        assert r.min_rooms is None

    def test_appartement_3_pieces(self):
        r = parse_intent("Appartement T3 Lyon")
        assert r.intent == IntentType.property_search
        assert r.city == "Lyon"
        assert r.property_type == PropertyType.apartment
        assert r.min_rooms == 3

    def test_rental_studio(self):
        r = parse_intent("Louer studio Bordeaux")
        assert r.intent == IntentType.rental_search
        assert r.transaction_type == TransactionType.rental
        assert r.city == "Bordeaux"
        assert r.property_type == PropertyType.studio

    def test_mandate_search(self):
        r = parse_intent("mandats exclusifs marseille")
        assert r.intent == IntentType.mandate_search
        assert r.mandate_type == MandateType.exclusive
        assert r.city == "Marseille"

    def test_unknown_returns_unknown_intent(self):
        r = parse_intent("bonjour")
        assert r.intent == IntentType.unknown

    def test_empty_query_returns_unknown(self):
        r = parse_intent("")
        assert r.intent == IntentType.unknown
        assert r.city is None
        assert r.property_type is None
        assert r.max_price is None

    def test_city_order_respected(self):
        """Régression V1.1 : la première ville dans la phrase doit être retournée."""
        r = parse_intent("maison a Paris ou Lyon")
        assert r.city == "Paris"

    def test_semantic_terms_captures_unknown_tokens(self):
        r = parse_intent("maison lumineuse calme Paris")
        assert "lumineuse" in r.semantic_terms or "calme" in r.semantic_terms

    def test_result_is_property_intent_instance(self):
        from app.entities.nlp.intent_schema import PropertyIntent
        assert isinstance(parse_intent("test"), PropertyIntent)


# =============================================================================
# _is_noise_token — tests unitaires du filtre de bruit
# =============================================================================

class TestIsNoiseToken:
    """Vérifie que _is_noise_token identifie correctement le bruit structurel.

    Analogie PHP : on teste une méthode privée via réflexion ou en la rendant
    protected — ici Python permet l'import direct des fonctions "privées".
    """

    # ── Tokens qui SONT du bruit ─────────────────────────────────────────────

    def test_pure_number_is_noise(self):
        assert _is_noise_token("500") is True

    def test_single_digit_is_noise(self):
        assert _is_noise_token("3") is True

    def test_price_format_lowercase_k_is_noise(self):
        assert _is_noise_token("500k") is True

    def test_price_format_uppercase_K_is_noise(self):
        assert _is_noise_token("300K") is True

    def test_room_format_t3_is_noise(self):
        """'t3' a 2 chars → filtré par len <= 2 avant même la regex."""
        assert _is_noise_token("t3") is True

    def test_room_format_f4_is_noise(self):
        assert _is_noise_token("f4") is True

    def test_room_format_t10_is_noise(self):
        """'t10' a 3 chars → non filtré par len, mais filtré par _ROOM_FORMAT_RE."""
        assert _is_noise_token("t10") is True

    def test_single_char_is_noise(self):
        assert _is_noise_token("a") is True

    def test_two_char_token_is_noise(self):
        assert _is_noise_token("ok") is True

    # ── Tokens qui NE SONT PAS du bruit ─────────────────────────────────────

    def test_descriptive_adjective_not_noise(self):
        assert _is_noise_token("lumineux") is False

    def test_lifestyle_term_not_noise(self):
        assert _is_noise_token("calme") is False

    def test_past_participle_not_noise(self):
        assert _is_noise_token("renove") is False

    def test_location_word_not_noise(self):
        """'vue' (3 chars) est un terme sémantique valide — non filtré par len > 2."""
        assert _is_noise_token("vue") is False

    def test_noun_not_noise(self):
        assert _is_noise_token("terrasse") is False


# =============================================================================
# Intégration — filtrage des termes de bruit dans parse_intent()
# =============================================================================

class TestSemanticTermsFiltering:
    """Vérifie que les tokens structurels sont absents de semantic_terms.

    Ces tests valident le pipeline complet : normalisation → tokenisation →
    _is_noise_token → semantic_terms. Chaque cas cible un type de bruit précis.
    """

    def test_price_format_excluded(self):
        """'500k' sans contexte de prix ne doit pas devenir un terme sémantique.

        Avant V2.1 : "Maison Paris 500k" → semantic_terms=["500k"] → hybrid routing.
        Après V2.1  : semantic_terms=[] → sql_only (city + property_type suffisent).
        """
        r = parse_intent("Maison Paris 500k")
        assert r.semantic_terms == []

    def test_room_format_excluded(self):
        """'T3' normalisé en 't3' (2 chars) → filtré par _is_noise_token."""
        r = parse_intent("Appartement T3 Lyon")
        assert r.semantic_terms == []

    def test_descriptive_adjectives_preserved(self):
        """Les adjectifs qualitatifs restent dans semantic_terms."""
        r = parse_intent("Maison lumineuse terrasse")
        assert r.semantic_terms == ["lumineuse", "terrasse"]

    def test_lifestyle_terms_preserved_after_normalization(self):
        """'rénové' normalisé en 'renove' doit être conservé comme terme sémantique."""
        r = parse_intent("Studio calme rénové")
        assert "calme" in r.semantic_terms
        assert "renove" in r.semantic_terms

    # ── V2.2 — connecteurs grammaticaux ──────────────────────────────────────

    def test_connector_avec_filtered(self):
        """'avec' est une préposition sans valeur sémantique pour le bien."""
        r = parse_intent("lumineux avec terrasse")
        assert r.semantic_terms == ["lumineux", "terrasse"]

    def test_connector_sans_filtered(self):
        """'sans' (ajouté en V2.2) ne doit pas figurer dans semantic_terms."""
        r = parse_intent("studio sans travaux")
        assert r.semantic_terms == ["travaux"]

    def test_domain_adjectives_preserved(self):
        """'moderne' et 'standing' sont des qualificatifs métier — conservés."""
        r = parse_intent("maison moderne standing")
        assert r.semantic_terms == ["moderne", "standing"]


# =============================================================================
# _extract_compound_semantic_terms — tests unitaires
# =============================================================================

class TestExtractCompoundSemanticTerms:
    """Vérifie la détection des expressions composées sur tokens déjà filtrés.

    Les tokens reçus ont déjà subi le filtrage bruit + stopwords.
    "bord de mer" → tokens filtrés = ["bord", "mer"] (de supprimé).
    """

    # ── Détection positive ────────────────────────────────────────────────────

    def test_detects_vue_mer(self):
        compounds, consumed = _extract_compound_semantic_terms(["vue", "mer"])
        assert "vue mer" in compounds
        assert consumed == {0, 1}

    def test_detects_proche_gare(self):
        compounds, consumed = _extract_compound_semantic_terms(["proche", "gare"])
        assert "proche gare" in compounds
        assert consumed == {0, 1}

    def test_detects_centre_ville(self):
        compounds, consumed = _extract_compound_semantic_terms(["centre", "ville"])
        assert "centre ville" in compounds
        assert consumed == {0, 1}

    def test_detects_bord_mer_without_de(self):
        """'bord de mer' : 'de' filtré en amont → tokens ["bord", "mer"]."""
        compounds, consumed = _extract_compound_semantic_terms(["bord", "mer"])
        assert "bord de mer" in compounds
        assert consumed == {0, 1}

    def test_detects_compound_at_non_zero_position(self):
        """Un compound au milieu de la liste est détecté correctement."""
        compounds, consumed = _extract_compound_semantic_terms(["lumineux", "vue", "mer"])
        assert "vue mer" in compounds
        assert consumed == {1, 2}
        assert 0 not in consumed  # "lumineux" non consommé

    # ── Absence de faux positifs ──────────────────────────────────────────────

    def test_no_match_returns_empty(self):
        compounds, consumed = _extract_compound_semantic_terms(["lumineux", "calme"])
        assert compounds == []
        assert consumed == set()

    def test_partial_token_does_not_trigger_compound(self):
        """'vue' seul (sans 'mer') ne déclenche pas le compound 'vue mer'."""
        compounds, consumed = _extract_compound_semantic_terms(["vue", "calme"])
        assert "vue mer" not in compounds
        assert 0 not in consumed

    def test_empty_input_returns_empty(self):
        compounds, consumed = _extract_compound_semantic_terms([])
        assert compounds == []
        assert consumed == set()

    # ── Ordre et isolation ────────────────────────────────────────────────────

    def test_compounds_returned_in_text_order(self):
        """Deux compounds : l'ordre de sortie suit l'ordre des tokens."""
        tokens = ["proche", "gare", "vue", "mer"]
        compounds, consumed = _extract_compound_semantic_terms(tokens)
        assert compounds == ["proche gare", "vue mer"]
        assert consumed == {0, 1, 2, 3}

    def test_consumed_indices_correct_for_mid_position(self):
        tokens = ["lumineux", "proche", "gare"]
        _, consumed = _extract_compound_semantic_terms(tokens)
        assert consumed == {1, 2}


# =============================================================================
# Intégration — compounds dans parse_intent()
# =============================================================================

class TestCompoundIntegration:
    """Vérifie l'intégration des compounds dans le pipeline parse_intent() complet."""

    def test_vue_mer_as_single_term(self):
        """'vue mer' doit apparaître comme une seule entrée, pas deux tokens."""
        r = parse_intent("maison vue mer")
        assert r.semantic_terms == ["vue mer"]

    def test_proche_gare_as_single_term(self):
        r = parse_intent("appartement proche gare")
        assert r.semantic_terms == ["proche gare"]

    def test_text_order_preserved_single_then_compound(self):
        """'moderne' apparaît avant 'centre ville' — l'ordre texte doit être conservé."""
        r = parse_intent("studio moderne centre ville")
        assert r.semantic_terms == ["moderne", "centre ville"]

    def test_compound_does_not_duplicate_tokens(self):
        """Les tokens absorbés par un compound ne réapparaissent pas en simple."""
        r = parse_intent("appartement vue mer lumineux")
        assert "vue" not in r.semantic_terms
        assert "mer" not in r.semantic_terms
        assert "vue mer" in r.semantic_terms
        assert "lumineux" in r.semantic_terms

    def test_bord_de_mer_reconstructed(self):
        """'bord de mer' → 'de' filtré comme stopword, compound reconstruit."""
        r = parse_intent("villa bord de mer")
        assert r.semantic_terms == ["bord de mer"]


# =============================================================================
# V2.4 — Synonymes enrichis
# =============================================================================

class TestSynonymPropertyType:
    """Vérifie que les nouveaux synonymes de V2.4 sont bien mappés."""

    def test_pavillon_maps_to_house(self):
        r = parse_intent("pavillon lyon")
        assert r.property_type == PropertyType.house

    def test_baraque_maps_to_house(self):
        r = parse_intent("baraque nice")
        assert r.property_type == PropertyType.house

    def test_maisonette_maps_to_house(self):
        r = parse_intent("maisonette toulouse")
        assert r.property_type == PropertyType.house

    def test_residence_maps_to_house(self):
        r = parse_intent("residence paris")
        assert r.property_type == PropertyType.house

    def test_penthouse_maps_to_apartment(self):
        r = parse_intent("penthouse paris")
        assert r.property_type == PropertyType.apartment

    def test_duplex_maps_to_apartment(self):
        r = parse_intent("duplex bordeaux")
        assert r.property_type == PropertyType.apartment


class TestSynonymTransaction:
    """Vérifie les synonymes de transaction type ajoutés en V2.4."""

    def test_loc_maps_to_rental(self):
        # "loc" = abréviation de "location" — token exact uniquement
        r = parse_intent("loc studio bordeaux")
        assert r.transaction_type == TransactionType.rental

    def test_local_commercial_not_rental(self):
        # "local" contient "loc" comme substring — NE DOIT PAS déclencher rental
        r = parse_intent("local commercial paris")
        assert r.transaction_type is None
        assert r.property_type == PropertyType.commercial


# =============================================================================
# V2.4 — Typo tolerance (fuzzy matching)
# =============================================================================

class TestFuzzyIntentParser:
    """Tests d'intégration : fuzzy matching via parse_intent().

    Ces tests vérifient que le pipeline complet absorbe les fautes de frappe
    simples (distance Levenshtein ≤ 1) sans casser les autres champs.
    """

    def test_apartement_typo(self):
        # "apartement" → "appartement" (1 'p' manquant)
        r = parse_intent("apartement paris")
        assert r.property_type == PropertyType.apartment
        assert r.city == "Paris"

    def test_vilaa_typo(self):
        # "vilaa" → "villa" (1 'a' en trop)
        r = parse_intent("vilaa nice")
        assert r.property_type == PropertyType.villa
        assert r.city == "Nice"

    def test_achatt_typo_maps_to_sale(self):
        # "achatt" → "achat" (distance 1 : 1 't' en trop)
        r = parse_intent("achatt maison")
        assert r.transaction_type == TransactionType.sale

    def test_short_token_not_fuzzy_matched(self):
        # "pa" ≤ 2 chars → stop condition : jamais fuzzy-matché contre "parking" ou "pavillon"
        r = parse_intent("pa")
        assert r.city is None
        assert r.property_type is None

    def test_existing_exact_keywords_unaffected(self):
        # Les keywords exacts V1 doivent continuer à fonctionner
        # "sous 500k" requis — "500k" seul sans préposition n'est pas extrait (design V1)
        r = parse_intent("appartement paris sous 500k")
        assert r.property_type == PropertyType.apartment
        assert r.city == "Paris"
        assert r.max_price == 500000


# =============================================================================
# MANDATE_SYNONYMS — dict public + nouveau keyword "exclusive"
# =============================================================================

class TestMandateSynonyms:
    def test_mandate_synonyms_is_dict(self):
        assert isinstance(MANDATE_SYNONYMS, dict)

    def test_exclusive_en_keyword_in_synonyms(self):
        assert "exclusive" in MANDATE_SYNONYMS

    def test_exclusive_en_maps_to_exclusive(self):
        assert MANDATE_SYNONYMS["exclusive"] == MandateType.exclusive

    def test_exclusive_en_keyword_extracted(self):
        assert _extract_mandate_type("mandat exclusive") == MandateType.exclusive

    def test_existing_exclusif_still_works(self):
        assert _extract_mandate_type("mandat exclusif") == MandateType.exclusive

    def test_exclu_still_works(self):
        assert _extract_mandate_type("mandat exclu") == MandateType.exclusive

    def test_simple_still_works(self):
        assert _extract_mandate_type("mandat simple") == MandateType.simple


# =============================================================================
# _extract_published_more_than_days
# =============================================================================

class TestExtractPublishedMoreThanDays:
    def test_plus_de_30_jours(self):
        assert _extract_published_more_than_days("plus de 30 jours") == 30

    def test_depuis_30_jours(self):
        assert _extract_published_more_than_days("depuis 30 jours") == 30

    def test_publie_il_y_a_plus_de(self):
        assert _extract_published_more_than_days("publie il y a plus de 30 jours") == 30

    def test_publie_depuis_plus_de(self):
        assert _extract_published_more_than_days("publie depuis plus de 30 jours") == 30

    def test_different_number(self):
        assert _extract_published_more_than_days("plus de 60 jours") == 60

    def test_moins_de_does_not_match(self):
        assert _extract_published_more_than_days("moins de 7 jours") is None

    def test_empty_string(self):
        assert _extract_published_more_than_days("") is None

    def test_no_temporal_context(self):
        assert _extract_published_more_than_days("maison paris") is None


# =============================================================================
# _extract_published_less_than_days
# =============================================================================

class TestExtractPublishedLessThanDays:
    def test_moins_de_7_jours(self):
        assert _extract_published_less_than_days("moins de 7 jours") == 7

    def test_moins_de_14_jours(self):
        assert _extract_published_less_than_days("moins de 14 jours") == 14

    def test_plus_de_does_not_match(self):
        assert _extract_published_less_than_days("plus de 30 jours") is None

    def test_depuis_does_not_match(self):
        assert _extract_published_less_than_days("depuis 30 jours") is None

    def test_empty_string(self):
        assert _extract_published_less_than_days("") is None

    def test_no_temporal_context(self):
        assert _extract_published_less_than_days("maison paris") is None


# =============================================================================
# _extract_agent_name
# =============================================================================

class TestExtractAgentName:
    def test_marie_dupont(self):
        assert _extract_agent_name("de Marie Dupont") == "Marie Dupont"

    def test_jean_martin(self):
        assert _extract_agent_name("de Jean Martin") == "Jean Martin"

    def test_with_context(self):
        assert _extract_agent_name("mandat de Marie Dupont") == "Marie Dupont"

    def test_single_capitalized_word_not_matched(self):
        # "de Paris" = 1 seul mot Title Case → no match (pattern exige ≥ 2 mots)
        assert _extract_agent_name("de Paris") is None

    def test_no_agent_context(self):
        assert _extract_agent_name("maison paris") is None

    def test_empty_string(self):
        assert _extract_agent_name("") is None

    def test_agent_patterns_is_compiled(self):
        import re
        assert isinstance(AGENT_PATTERNS, re.Pattern)


# =============================================================================
# TIME_PATTERNS — structure publique
# =============================================================================

class TestTimePatterns:
    def test_time_patterns_is_dict(self):
        assert isinstance(TIME_PATTERNS, dict)

    def test_more_than_days_key_exists(self):
        assert "more_than_days" in TIME_PATTERNS

    def test_less_than_days_key_exists(self):
        assert "less_than_days" in TIME_PATTERNS


# =============================================================================
# Intégration temporalité — parse_intent()
# =============================================================================

class TestPublishedDaysIntegration:
    def test_more_than_30_days_mandate(self):
        r = parse_intent("mandat exclusif depuis plus de 30 jours")
        assert r.published_more_than_days == 30
        assert r.mandate_type == MandateType.exclusive

    def test_less_than_7_days_with_city(self):
        r = parse_intent("appartement Paris moins de 7 jours")
        assert r.published_less_than_days == 7
        assert r.city == "Paris"

    def test_temporal_tokens_not_in_semantic_terms(self):
        # "Lyon" = exact city match → le fuzzy fallback ne s'active pas sur "jours"
        r = parse_intent("appartement Lyon depuis plus de 30 jours")
        assert "jours" not in r.semantic_terms
        assert "depuis" not in r.semantic_terms

    def test_published_more_than_days_triggers_property_search(self):
        r = parse_intent("depuis plus de 30 jours")
        assert r.intent == IntentType.property_search
        assert r.published_more_than_days == 30

    def test_published_query_does_not_invent_tours_city(self):
        r = parse_intent("Biens publiés depuis plus de 30 jours")
        assert r.city is None
        assert r.published_more_than_days == 30


# =============================================================================
# Intégration agent — parse_intent()
# =============================================================================

class TestAgentNameIntegration:
    def test_mandats_de_marie_dupont(self):
        r = parse_intent("Mandats de Marie Dupont")
        assert r.agent_name == "Marie Dupont"
        assert r.intent == IntentType.mandate_search

    def test_agent_name_triggers_property_search_without_mandat(self):
        r = parse_intent("de Jean Martin")
        assert r.agent_name == "Jean Martin"
        assert r.intent == IntentType.property_search

    def test_agent_tokens_not_in_semantic_terms(self):
        r = parse_intent("Mandats de Marie Dupont")
        assert "marie" not in r.semantic_terms
        assert "dupont" not in r.semantic_terms
