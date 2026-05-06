"""
Geography — Proximity (bounding box + distance filter)
=======================================================

Logique pure de recherche de proximité géographique.
Aucune dépendance externe — stdlib math uniquement.

APPROCHE : SQL bounding box + haversine Python
----------------------------------------------
PostgreSQL sans PostGIS ne peut pas calculer des distances géographiques en SQL.
On procède donc en deux étapes :

    1. SQL bounding box (carré géographique)
       Filtre rapide pour réduire le dataset de ~10 000 biens à ~50-200 candidats.
       Un carré est toujours plus grand que le cercle → pas de faux négatifs.

    2. Haversine Python (cercle précis)
       Filtre les candidats de l'étape 1 par distance réelle.
       Utilise haversine_distance_km() — implémentée dans distance.py.

V2 roadmap
----------
- Table communes INSEE (~35 000 communes avec centroïdes officiels)
- PostGIS ST_DWithin + index GiST → distance en SQL natif, scalable
"""

import math

from app.entities.geography.distance import haversine_distance_km


def compute_bounding_box(
    lat: float,
    lon: float,
    radius_km: float,
) -> tuple[float, float, float, float]:
    """Calcule un carré géographique (bounding box) autour d'un point GPS.

    Retourne (lat_min, lat_max, lon_min, lon_max).

    Formule :
        1° de latitude  ≈ 111 km (constant sur la Terre)
        1° de longitude ≈ 111 km × cos(latitude)  (varie selon la latitude)

    Le carré est plus grand que le cercle de rayon radius_km :
    les coins du carré sont à radius_km × √2 du centre.
    Le filtre haversine appliqué ensuite affine au cercle réel.

    Args:
        lat: Latitude du centre (degrés décimaux).
        lon: Longitude du centre (degrés décimaux).
        radius_km: Rayon du cercle de recherche en kilomètres.

    Returns:
        (lat_min, lat_max, lon_min, lon_max)
    """
    delta_lat = radius_km / 111.0
    delta_lon = radius_km / (111.0 * math.cos(math.radians(lat)))
    return (
        lat - delta_lat,
        lat + delta_lat,
        lon - delta_lon,
        lon + delta_lon,
    )


def filter_by_distance(
    properties: list,
    center_lat: float,
    center_lon: float,
    radius_km: float,
) -> list:
    """Filtre une liste de biens pour ne garder que ceux dans le rayon donné.

    Applique haversine_distance_km() sur chaque bien.
    Ignore les biens sans coordonnées GPS (latitude/longitude None).

    C'est le filtre de précision après la bounding box SQL :
        bounding box → carré géographique (~50-200 candidats)
        haversine    → cercle géographique précis (résultats finaux)

    Args:
        properties: Liste de biens candidats (issus de la bounding box SQL).
        center_lat: Latitude du centre de la recherche.
        center_lon: Longitude du centre de la recherche.
        radius_km: Rayon de recherche en kilomètres.

    Returns:
        Sous-liste des biens dont la distance au centre est ≤ radius_km.
    """
    return [
        p for p in properties
        if p.latitude is not None
        and p.longitude is not None
        and haversine_distance_km(center_lat, center_lon, p.latitude, p.longitude) <= radius_km
    ]
