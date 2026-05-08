"""
Schemas de réponse — Property Search API
=========================================

POURQUOI CE FICHIER EXISTE ?
------------------------------
Les objets SQLAlchemy (Property, Mandate…) sont des représentations de la base
de données. Ce sont des objets INTERNES au backend — ils ne sont pas faits pour
être exposés directement à un client HTTP.

Ce fichier définit les CONTRATS DE SORTIE de l'API : ce que le client reçoit,
quel que soit ce que contient la base.

    ORM Model (Property)        → données internes, schéma DB
    Pydantic Schema (PropertyResult) → données publiques, contrat API

PYDANTIC V2 — from_attributes
--------------------------------
Par défaut, Pydantic v2 ne sait pas lire un objet Python classique (comme une
instance SQLAlchemy). Il attend un dict ou des kwargs.

    from_attributes=True → active la lecture des attributs Python directement.

    # Sans from_attributes :
    PropertyResult(id=p.id, city=p.city, ...)  # manuel, verbeux

    # Avec from_attributes :
    PropertyResult.model_validate(p)  # Pydantic lit p.id, p.city… automatiquement
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.entities.nlp.intent_schema import PropertyIntent
from app.entities.search.query_types import QueryResolution


class PropertySearchResult(BaseModel):
    """Représentation JSON d'un bien immobilier retourné par l'API de recherche.

    Renommé PropertyResult → PropertySearchResult pour lever toute ambiguïté :
    il existe un ORM Property, un schéma PropertyIntent, un moteur de recherche —
    "PropertySearchResult" indique sans ambiguïté : résultat de recherche, format API.
    """

    # ConfigDict remplace class Config en Pydantic v2.
    #
    # from_attributes=True : permet PropertySearchResult.model_validate(orm_object)
    # → Pydantic lit les attributs de l'objet SQLAlchemy directement.
    model_config = ConfigDict(from_attributes=True)

    id: int
    city: str

    # ── Renommage de champ : "type" → "property_type" ──────────────────────────
    #
    # Property.type est le nom de la colonne SQLAlchemy.
    # "type" est un nom générique et potentiellement confus dans une API JSON.
    # On l'expose sous le nom "property_type" pour plus de clarté.
    #
    # PIÈGE PYDANTIC V2 + FASTAPI :
    # FastAPI sérialise les réponses avec by_alias=True — donc si on utilise
    # alias="type", la clé JSON de sortie serait "type" et non "property_type".
    #
    # Pydantic v2 distingue deux options :
    #   alias           = utilisé à la FOIS en lecture ET en sortie (by_alias=True)
    #   validation_alias = utilisé UNIQUEMENT en lecture (input / ORM)
    #                      → la sortie utilise le nom du champ Python : "property_type" ✓
    #
    # validation_alias="type" signifie :
    #   → En LECTURE  : lire l'attribut .type de l'objet ORM     (via from_attributes)
    #   → En SORTIE   : sérialiser sous "property_type" (nom du champ, pas de l'alias)
    #
    property_type: str = Field(validation_alias="type")

    transaction_type: str

    # Nullable : mandate_price peut être None si le bien n'a pas encore de prix.
    # Decimal → float : Numeric(12,2) en PostgreSQL retourne Decimal en Python.
    # Pydantic convertit automatiquement Decimal → float lors de la validation.
    mandate_price: float | None = None

    rooms_count: int | None = None

    # datetime ISO 8601 en JSON : "2024-01-15T10:30:00+00:00"
    # FastAPI + Pydantic sérialisent datetime automatiquement — pas besoin de .isoformat()
    created_at: datetime

    # Score de pertinence sémantique : None pour sql_only, float [0,1] pour semantic/hybrid.
    # Permet au client de trier, filtrer ou afficher une barre de confiance.
    score: float | None = None

    # Description française du bien (locale="fr"). None si absente en base.
    description_fr: str | None = None


class PropertySearchResponse(BaseModel):
    """Enveloppe complète de réponse pour /properties/search.

    Contient :
    - query            : la phrase originale de l'utilisateur
    - parsed_intent    : l'intent NLP extrait (transparence du parsing)
    - query_resolution : la stratégie choisie par le moteur (transparence de la décision)
    - count            : nombre de résultats sur la page courante (= len(results))
    - page             : numéro de page courant (1-indexé)
    - per_page         : nombre de résultats par page demandé
    - total_pages      : nombre total de pages (calculé depuis total_count)
    - results          : liste des biens de la page courante

    Pourquoi exposer parsed_intent ET query_resolution ?
    - parsed_intent    : ce que le NLP a compris de la phrase (ville, prix, type…)
    - query_resolution : comment le moteur a décidé d'exécuter (SQL, sémantique, hybride)
    - Si les résultats sont inattendus, ces deux champs révèlent exactement POURQUOI.
    - Portfolio : démontre visuellement le pipeline complet NLP → Resolver → Executor.
    """

    query: str
    parsed_intent: PropertyIntent
    query_resolution: QueryResolution
    count: int
    page: int
    per_page: int
    total_pages: int
    results: list[PropertySearchResult]
    nearby_city: str | None = None
    # Ville cible de la recherche de proximité. None si recherche exacte.
    search_radius_km: int | None = None
    # Rayon utilisé pour la recherche de proximité. None si recherche exacte.
    expanded_cities: list[str] = []
    # Villes distinctes présentes dans les résultats, triées alphabétiquement.
    # Ex : ["Clairefontaine-en-Yvelines", "Les Essarts-le-Roi", "Rambouillet"]
    # Vide pour une recherche exacte (city) ou sans filtre localisation.
