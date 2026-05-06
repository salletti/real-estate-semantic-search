"""
Property Text Builder
=====================

RÔLE
----
Construire le texte sémantique représentant un bien immobilier — utilisé à deux endroits :
    1. scripts/index_properties_to_qdrant.py        → indexation Qdrant (au moment du build)
    2. SearchPropertyUsecase (_hybrid_search)        → scoring local des candidats SQL

L'extraction dans ce module partagé est critique pour la cohérence de la recherche :
si le texte d'indexation et le texte de scoring divergent, les vecteurs comparés
n'habitent plus le même espace sémantique → dégradation silencieuse de la qualité.

ANALOGIE SYMFONY
-----------------
Équivalent d'un ValueObject builder partagé entre une commande Console (indexation)
et un service métier (recherche hybride) :

    class PropertyTextBuilder
    {
        public function build(Property $p): string
        {
            return implode(' ', array_filter([
                $p->getType(), $p->getCity(), ...
            ]));
        }
    }
"""

from app.adapters.gateways.db.models.property import Property


def build_semantic_text(prop: Property) -> str:
    """Construit le texte sémantique enrichi représentant un bien.

    Mélange données structurées et description libre pour un embedding riche.
    Exemple : "house Paris 4 pièces 450000€. Bel appartement lumineux avec terrasse..."

    Note : accède à `prop.descriptions` — requiert un eager load (selectinload)
    si appelé dans un contexte SQLAlchemy async.

    Args:
        prop: Objet Property SQLAlchemy avec descriptions chargées.

    Returns:
        Texte concaténé, stripped. Chaîne vide uniquement si tous les champs sont None/vides.
    """
    description_text = prop.descriptions[0].description if prop.descriptions else ""

    parts = [
        prop.type,
        prop.city,
        f"{prop.rooms_count} pièces" if prop.rooms_count else "",
        f"{int(prop.mandate_price or 0)}€" if prop.mandate_price else "",
        description_text,
    ]
    return " ".join(p for p in parts if p).strip()
