"""
Cosine Similarity
=================

RÔLE
----
Mesurer la proximité sémantique entre deux vecteurs d'embedding.

Utilisé pour scorer les candidats SQL par rapport à la query sémantique
dans la stratégie hybrid de SearchPropertyUsecase.

FORMULE
-------
    cosine_similarity(a, b) = (a · b) / (||a|| × ||b||)

En pratique : embed_text() retourne des vecteurs déjà L2-normalisés
(normalize_embeddings=True), donc cosine = dot product.
La formule complète est conservée pour robustesse si la source change.

ANALOGIE PHP
------------
Équivalent d'un helper statique de calcul vectoriel, sans état :

    class CosineSimilarity
    {
        public static function compute(array $a, array $b): float
        {
            $dot   = array_sum(array_map(fn($x, $y) => $x * $y, $a, $b));
            $normA = sqrt(array_sum(array_map(fn($x) => $x ** 2, $a)));
            $normB = sqrt(array_sum(array_map(fn($x) => $x ** 2, $b)));
            return ($normA * $normB === 0.0) ? 0.0 : $dot / ($normA * $normB);
        }
    }
"""

import numpy as np


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Calcule la similarité cosinus entre deux vecteurs d'embedding.

    Args:
        vec_a: Premier vecteur (list[float], n dimensions).
        vec_b: Second vecteur (list[float], même dimension que vec_a).

    Returns:
        float dans [-1, 1]. Retourne 0.0 si l'un des vecteurs est nul
        (cas dégénéré — évite une division par zéro silencieuse).
    """
    a = np.array(vec_a, dtype=np.float64)
    b = np.array(vec_b, dtype=np.float64)

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))
