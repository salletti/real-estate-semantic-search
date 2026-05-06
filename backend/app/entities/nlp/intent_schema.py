"""
NLP — Intent Schema V1 (pédagogique)
======================================

INTENT = QUOI ?
---------------
Un "intent" est la traduction structurée de l'intention d'un utilisateur.
Quand l'utilisateur tape "Maison à Paris sous 500k", on ne peut pas passer
ce texte brut à un repository SQLAlchemy — c'est une phrase, pas des données.

On l'analyse d'abord pour en extraire les champs utiles :
    city="Paris", property_type="house", max_price=500000

Ce schéma Pydantic est l'objet qui porte ces informations extraites.


POURQUOI NLP → JSON PLUTÔT QUE NLP → SQL DIRECT ?
---------------------------------------------------
NLP → SQL direct — ce qu'on N'utilise PAS :
  - Fragile : une variation de phrase casse la requête
  - Dangereux : risque d'injection SQL
  - Impossible à tester ou auditer

NLP → Intent JSON → Repository — notre approche :
  - L'intent est un objet Python testable indépendamment du SQL
  - Chaque couche a une responsabilité unique (principe SRP)
  - L'intent peut être loggé, stocké, rejoué


PYDANTIC = SYMFONY DTO + VALIDATOR
------------------------------------
En PHP/Symfony :

    class SearchRequest
    {
        #[Assert\\NotBlank]
        public string $city;
        public ?int $maxPrice = null;
    }
    $errors = $validator->validate($request);

En Python avec Pydantic — même logique, une seule classe :

    class PropertyIntent(BaseModel):
        city: str | None = None        # champ optionnel
        max_price: int | None = None   # validation du type automatique

    PropertyIntent(max_price="abc")  # → ValidationError : abc n'est pas int
    PropertyIntent(max_price="500000")  # → max_price=500000 (coercition str→int)


ENUM PYDANTIC = PHP 8.1 BACKED ENUM
--------------------------------------
PHP 8.1 :
    enum IntentType: string
    {
        case PropertySearch = 'property_search';
        case Unknown        = 'unknown';
    }
    $val = IntentType::PropertySearch->value; // → "property_search"

Python (str, Enum) — comportement identique :
    class IntentType(str, Enum):
        property_search = "property_search"
        unknown         = "unknown"

    IntentType.property_search == "property_search"  # → True
    # str, Enum : la valeur de l'enum EST la chaîne


ÉVOLUTION FUTURE (V2)
-----------------------
V1 : DTO simple à champs plats (ce fichier)
V2 : Constraint Graph — chaque champ devient une contrainte composable :

    # V1 (aujourd'hui)
    city: str | None = "Paris"

    # V2 (futur)
    locations: list[LocationConstraint] = [
        LocationConstraint(type="city", city="Paris"),
        LocationConstraint(type="city", city="Lyon"),
    ]
    location_operator: LogicalOperator = "or"

V2 permettra : "Paris ou Lyon", "zone de Rambouillet", "dans un rayon de 20km".
L'ajout se fera sans casser V1 — les champs V1 seront conservés avec auto-hydratation.
"""

from enum import Enum

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """Type d'intention détecté dans la requête utilisateur.

    PHP équivalent : enum IntentType: string { case PropertySearch = 'property_search'; ... }
    """

    property_search = "property_search"  # l'utilisateur cherche un bien à acheter
    mandate_search = "mandate_search"    # l'utilisateur parle de mandats (vue agence)
    rental_search = "rental_search"      # l'utilisateur cherche un bien à louer
    unknown = "unknown"                  # intention non reconnue


class PropertyType(str, Enum):
    """Type de bien immobilier.

    Correspond aux valeurs de la colonne 'type' dans la table 'properties'.
    """

    apartment = "apartment"    # appartement
    house = "house"            # maison
    villa = "villa"            # villa
    studio = "studio"          # studio
    loft = "loft"              # loft
    land = "land"              # terrain
    commercial = "commercial"  # local commercial
    parking = "parking"        # parking / garage


class TransactionType(str, Enum):
    """Type de transaction — correspond à 'transaction_type' dans properties."""

    sale = "sale"      # achat / vente
    rental = "rental"  # location


class MandateType(str, Enum):
    """Type de mandat immobilier.

    Exclusif : l'agence est seule à gérer la vente.
    Simple   : plusieurs agences peuvent vendre en parallèle.
    """

    exclusive = "exclusive"
    simple = "simple"


class PropertyIntent(BaseModel):
    """DTO structuré représentant l'intention extraite d'une requête en langage naturel.

    Analogie Symfony : un DTO de recherche hydraté depuis une phrase utilisateur
    plutôt que depuis les paramètres d'une requête HTTP.

    Tous les champs sont optionnels — un intent partiel est toujours valide.
    Le parseur remplit ce qu'il peut extraire, laisse None pour le reste.

    Exemple :
        "Maison à Paris sous 500k" → PropertyIntent(
            intent=IntentType.property_search,
            city="Paris",
            property_type=PropertyType.house,
            max_price=500000,
        )

    V1 — champs plats simples.
    V2 — certains champs évolueront vers des contraintes composables (voir docstring module).
    """

    intent: IntentType = IntentType.unknown
    llm_used: bool = False
    city: str | None = None
    nearby_city: str | None = None
    # "maison à côté de Rambouillet" → nearby_city="Rambouillet", city=None
    # Invariant : nearby_city XOR city (jamais les deux remplis simultanément).
    # La résolution géographique (centre GPS + rayon) se fait dans query_executor.py.
    search_radius_km: int | None = None
    # Rayon en km pour la recherche de proximité.
    # None si nearby_city est absent ; défaut 15 km si défini par le parseur.
    property_type: PropertyType | None = None
    max_price: int | None = None
    min_rooms: int | None = None
    mandate_type: MandateType | None = None
    transaction_type: TransactionType | None = None
    published_more_than_days: int | None = None
    published_less_than_days: int | None = None
    agent_name: str | None = None
    semantic_terms: list[str] = Field(
        default_factory=list,
        description="Tokens non reconnus — conservés pour recherche sémantique future (V2).",
    )

    def has_structured_filters(self) -> bool:
        """Indique si l'intent contient au moins un filtre structuré exploitable par SQL."""
        return any([
            self.city is not None,
            self.nearby_city is not None,
            self.property_type is not None,
            self.max_price is not None,
            self.min_rooms is not None,
            self.mandate_type is not None,
            self.transaction_type is not None,
            self.published_more_than_days is not None,
            self.published_less_than_days is not None,
            self.agent_name is not None,
        ])

    def has_semantic_terms(self) -> bool:
        """Indique si l'intent contient des termes pour la recherche sémantique."""
        return bool(self.semantic_terms)
