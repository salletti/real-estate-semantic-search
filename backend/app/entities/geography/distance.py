import math


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcule la distance orthodromique (à vol d’oiseau) entre deux points GPS.

    La formule de Haversine permet de calculer la distance entre deux points
    à la surface d'une sphère (la Terre ici), à partir de leurs coordonnées
    géographiques (latitude / longitude).

    Args:
        lat1: Latitude du point A (en degrés décimaux)
        lon1: Longitude du point A (en degrés décimaux)
        lat2: Latitude du point B (en degrés décimaux)
        lon2: Longitude du point B (en degrés décimaux)

    Returns:
        Distance entre les deux points en kilomètres (float)
    """

    # Rayon moyen de la Terre en kilomètres
    # (approximation standard utilisée dans la majorité des calculs géographiques)
    R = 6371.0

    # Conversion des coordonnées de degrés → radians
    # Les fonctions trigonométriques Python travaillent en radians
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    # Différences de latitude et longitude (en radians)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    # Formule de Haversine :
    # a représente la moitié du carré de la distance angulaire
    a = (
            math.sin(d_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )

    # ⚠️ Protection contre les erreurs de précision flottante
    # Exemple : a peut devenir légèrement > 1 (ex: 1.0000000002)
    # ce qui casserait sqrt(1 - a)
    a = min(1.0, max(0.0, a))

    # Calcul de l'angle central entre les deux points
    # atan2 est plus stable numériquement que asin
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # Distance finale (arc de cercle sur la sphère)
    distance = R * c

    return distance