#!/usr/bin/env python3
"""
Portfolio public — dataset de démonstration réaliste et anonymisé.

Symfony/Doctrine → SQLAlchemy async : table de correspondance rapide
─────────────────────────────────────────────────────────────────────
  $em->persist($obj)          →  session.add(obj)
  $em->flush()                →  await session.flush()   # INSERT sans COMMIT
  $em->flush() + COMMIT       →  await session.commit()
  new EntityManager(...)      →  AsyncSessionLocal() as session
  require autoload.php        →  sys.path.insert(0, ...)

flush() vs commit()
  flush()  : envoie les SQL au driver, génère les PK auto-incrémentées,
             reste dans la transaction ouverte — indispensable quand
             un objet suivant a besoin de parent.id.
  commit() : valide la transaction. Après commit, expire_on_commit=False
             (configuré dans session.py) préserve les attributs en mémoire
             sans déclencher de lazy-load — équivalent Doctrine post-flush.
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

# Rend le package `app` importable depuis backend/scripts/
# Équivalent : require __DIR__ . '/../../vendor/autoload.php'
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.adapters.gateways.db.session import AsyncSessionLocal  # factory AsyncSession réutilisée
from app.adapters.gateways.db.models.agent import Agent
from app.adapters.gateways.db.models.description import Description
from app.adapters.gateways.db.models.mandate import Mandate
from app.adapters.gateways.db.models.mandate_rental import MandateRental
from app.adapters.gateways.db.models.mandate_sale import MandateSale
from app.adapters.gateways.db.models.property import Property
from app.adapters.gateways.db.models.property_listing import PropertyListing


# ─── Helpers temporels ────────────────────────────────────────────────────────

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def days_ago(n: int) -> datetime:
    return utc_now() - timedelta(days=n)


def months_ago(n: int) -> datetime:
    return utc_now() - timedelta(days=n * 30)


# ─── AGENTS ───────────────────────────────────────────────────────────────────

AGENTS_RAW = [
    # (first_name, last_name, concession_slug, qualification_level)
    ("Marie",    "Dupont",   "agence-paris-8",              "senior"),
    ("Thomas",   "Martin",   "agence-lyon-centre",          "standard"),
    ("Sophie",   "Bernard",  "agence-bordeaux-chartrons",   "expert"),
    ("Nicolas",  "Lambert",  "agence-rennes-centre",        "standard"),
    ("Isabelle", "Rousseau", "agence-marseille-prado",      "senior"),
    ("Pierre",   "Lefevre",  "agence-toulouse-capitole",    "standard"),
    ("Camille",  "Moreau",   "agence-nantes-centre",        "junior"),
    ("Antoine",  "Dubois",   "agence-le-havre-maritime",    "standard"),
    ("Julie",    "Petit",    "agence-boulogne-seine",       "senior"),
    ("Maxime",   "Girard",   "agence-saint-denis-centre",   "standard"),
]


def make_agents() -> list[Agent]:
    agents = []
    for i, (fn, ln, slug, level) in enumerate(AGENTS_RAW):
        agents.append(Agent(
            first_name=fn,
            last_name=ln,
            concession_slug=slug,
            qualification_level=level,
            status="active",
            activated_at=months_ago(12 + i * 2),
        ))
    return agents


CITY_COORDS: dict[str, tuple[float, float]] = {
    # ── Grandes villes ────────────────────────────────────────────────────────
    "Paris":                 (48.8566,  2.3522),
    "Lyon":                  (45.7640,  4.8357),
    "Bordeaux":              (44.8378, -0.5792),
    "Rennes":                (48.1173, -1.6778),
    "Le Havre":              (49.4944,  0.1079),
    "Boulogne-Billancourt":  (48.8397,  2.2399),
    "Saint-Denis":           (48.9362,  2.3574),
    "Toulouse":              (43.6047,  1.4442),
    "Marseille":             (43.2965,  5.3698),
    "Nantes":                (47.2184, -1.5536),
    # ── Communes proches de Paris (~6-10 km) ──────────────────────────────────
    "Vincennes":             (48.8474,  2.4384),   # ~6 km E
    "Neuilly-sur-Seine":     (48.8850,  2.2661),   # ~7 km W
    "Levallois-Perret":      (48.8937,  2.2874),   # ~8 km NW
    "Montreuil":             (48.8638,  2.4483),   # ~8 km E
    # ── Communes proches de Lyon (~4-5 km) ───────────────────────────────────
    "Villeurbanne":          (45.7715,  4.8892),   # ~4 km E
    "Caluire-et-Cuire":      (45.8068,  4.8464),   # ~5 km N
    # ── Communes proches de Marseille (~9-10 km) ─────────────────────────────
    "Allauch":               (43.3352,  5.4797),   # ~10 km NE
    "Plan-de-Cuques":        (43.3367,  5.4669),   # ~9 km NE
    # ── Communes proches de Bordeaux (~5-6 km) ───────────────────────────────
    "Mérignac":              (44.8279, -0.6432),   # ~5 km W
    "Pessac":                (44.8057, -0.6312),   # ~6 km SW
    # ── Communes proches de Toulouse (~5-8 km) ───────────────────────────────
    "Blagnac":               (43.6353,  1.3937),   # ~5 km NW
    "Colomiers":             (43.6108,  1.3393),   # ~8 km W
    # ── Communes proches de Nantes (~4-5 km) ─────────────────────────────────
    "Saint-Herblain":        (47.2120, -1.5994),   # ~4 km W
    "Rezé":                  (47.1860, -1.5566),   # ~5 km S
    # ── Communes proches de Rennes (~5 km) ───────────────────────────────────
    "Cesson-Sévigné":        (48.1175, -1.6024),   # ~5 km E
}


# ─── PROPERTIES ───────────────────────────────────────────────────────────────
# Chaque tuple :
# (uid, type, sub_type, status, transaction_type,
#  city, postal_code, rooms, surface, mandate_price,
#  is_prestige, created_days_ago, agent_index)

PROPERTIES_RAW = [
    # ── PARIS ──────────────────────────────────────────────────────────────────
    ("PROP-PAR-001", "apartment", "T2",      "available", "sale",
     "Paris", "75008", 2,  42.0, Decimal("385000"), False, 45,  0),
    ("PROP-PAR-002", "apartment", "T3",      "available", "sale",
     "Paris", "75008", 3,  68.0, Decimal("620000"), True,  60,  0),
    ("PROP-PAR-003", "apartment", "T4",      "sold",      "sale",
     "Paris", "75011", 4,  89.0, Decimal("750000"), False, 180, 0),
    ("PROP-PAR-004", "apartment", "T2",      "available", "rental",
     "Paris", "75019", 2,  38.0, Decimal("1350"),   False, 30,  0),
    ("PROP-PAR-005", "studio",    None,      "available", "sale",
     "Paris", "75005", 1,  22.0, Decimal("198000"), False, 20,  0),
    ("PROP-PAR-006", "studio",    None,      "available", "rental",
     "Paris", "75014", 1,  19.5, Decimal("920"),    False, 15,  0),
    ("PROP-PAR-007", "house",     None,      "available", "sale",
     "Paris", "75020", 5, 130.0, Decimal("1180000"),True,  90,  0),
    ("PROP-PAR-008", "parking",   None,      "available", "sale",
     "Paris", "75017", 1,  12.0, Decimal("28000"),  False, 10,  0),

    # ── LYON ───────────────────────────────────────────────────────────────────
    ("PROP-LYO-001", "apartment", "T3",      "available", "sale",
     "Lyon",  "69001", 3,  72.0, Decimal("390000"), False, 55,  1),
    ("PROP-LYO-002", "apartment", "T2",      "rented",    "rental",
     "Lyon",  "69003", 2,  45.0, Decimal("850"),    False, 120, 1),
    ("PROP-LYO-003", "studio",    None,      "available", "sale",
     "Lyon",  "69007", 1,  26.0, Decimal("145000"), False, 40,  1),
    ("PROP-LYO-004", "house",     None,      "available", "sale",
     "Lyon",  "69005", 5, 140.0, Decimal("680000"), False, 75,  1),
    ("PROP-LYO-005", "commercial","boutique","available", "sale",
     "Lyon",  "69002", 1,  55.0, Decimal("280000"), False, 30,  1),

    # ── BORDEAUX ───────────────────────────────────────────────────────────────
    ("PROP-BDX-001", "apartment", "T3",      "available", "sale",
     "Bordeaux", "33000", 3,  78.0, Decimal("420000"), False, 35,  2),
    ("PROP-BDX-002", "apartment", "T2",      "available", "rental",
     "Bordeaux", "33000", 2,  48.0, Decimal("900"),    False, 25,  2),
    ("PROP-BDX-003", "apartment", "T4",      "sold",      "sale",
     "Bordeaux", "33800", 4,  95.0, Decimal("510000"), False, 200, 2),
    ("PROP-BDX-004", "studio",    None,      "available", "sale",
     "Bordeaux", "33200", 1,  24.0, Decimal("158000"), False, 18,  2),
    ("PROP-BDX-005", "house",     None,      "available", "sale",
     "Bordeaux", "33300", 4, 115.0, Decimal("595000"), False, 65,  2),

    # ── RENNES ─────────────────────────────────────────────────────────────────
    ("PROP-REN-001", "apartment", "T3",      "available", "sale",
     "Rennes", "35000", 3,  70.0, Decimal("295000"), False, 50,  3),
    ("PROP-REN-002", "apartment", "T2",      "available", "rental",
     "Rennes", "35000", 2,  44.0, Decimal("720"),    False, 22,  3),
    ("PROP-REN-003", "studio",    None,      "available", "sale",
     "Rennes", "35200", 1,  20.0, Decimal("112000"), False, 14,  3),
    ("PROP-REN-004", "studio",    None,      "available", "rental",
     "Rennes", "35000", 1,  18.5, Decimal("540"),    False, 8,   3),
    ("PROP-REN-005", "house",     None,      "available", "sale",
     "Rennes", "35700", 5, 128.0, Decimal("420000"), False, 80,  3),

    # ── LE HAVRE ───────────────────────────────────────────────────────────────
    ("PROP-LHA-001", "apartment", "T2",      "available", "sale",
     "Le Havre", "76600", 2,  50.0, Decimal("148000"), False, 42,  7),
    ("PROP-LHA-002", "apartment", "T3",      "available", "rental",
     "Le Havre", "76600", 3,  65.0, Decimal("750"),    False, 28,  7),
    ("PROP-LHA-003", "studio",    None,      "available", "sale",
     "Le Havre", "76600", 1,  21.0, Decimal("92000"),  False, 12,  7),
    ("PROP-LHA-004", "house",     None,      "sold",      "sale",
     "Le Havre", "76610", 4, 105.0, Decimal("285000"), False, 150, 7),

    # ── BOULOGNE-BILLANCOURT ───────────────────────────────────────────────────
    ("PROP-BOU-001", "apartment", "T3",      "available", "sale",
     "Boulogne-Billancourt", "92100", 3,  75.0, Decimal("720000"), True,  55,  8),
    ("PROP-BOU-002", "apartment", "T2",      "available", "sale",
     "Boulogne-Billancourt", "92100", 2,  52.0, Decimal("490000"), False, 40,  8),
    ("PROP-BOU-003", "apartment", "T4",      "available", "rental",
     "Boulogne-Billancourt", "92100", 4,  98.0, Decimal("2400"),   False, 20,  8),
    ("PROP-BOU-004", "studio",    None,      "available", "sale",
     "Boulogne-Billancourt", "92100", 1,  28.0, Decimal("248000"), False, 15,  8),
    ("PROP-BOU-005", "house",     None,      "available", "sale",
     "Boulogne-Billancourt", "92100", 6, 180.0, Decimal("1450000"),True,  100, 8),

    # ── SAINT-DENIS ────────────────────────────────────────────────────────────
    ("PROP-SDN-001", "apartment", "T3",      "available", "sale",
     "Saint-Denis", "93200", 3,  67.0, Decimal("235000"), False, 38,  9),
    ("PROP-SDN-002", "apartment", "T2",      "available", "rental",
     "Saint-Denis", "93200", 2,  42.0, Decimal("850"),    False, 25,  9),
    ("PROP-SDN-003", "studio",    None,      "available", "sale",
     "Saint-Denis", "93200", 1,  19.0, Decimal("98000"),  False, 10,  9),
    ("PROP-SDN-004", "house",     None,      "available", "sale",
     "Saint-Denis", "93200", 4,  92.0, Decimal("310000"), False, 60,  9),

    # ── TOULOUSE ───────────────────────────────────────────────────────────────
    ("PROP-TLS-001", "apartment", "T3",      "available", "sale",
     "Toulouse", "31000", 3,  72.0, Decimal("310000"), False, 45,  5),
    ("PROP-TLS-002", "apartment", "T2",      "rented",    "rental",
     "Toulouse", "31000", 2,  46.0, Decimal("780"),    False, 130, 5),
    ("PROP-TLS-003", "studio",    None,      "available", "sale",
     "Toulouse", "31300", 1,  23.0, Decimal("128000"), False, 18,  5),
    ("PROP-TLS-004", "house",     None,      "available", "sale",
     "Toulouse", "31200", 5, 132.0, Decimal("480000"), False, 70,  5),
    ("PROP-TLS-005", "commercial","bureau",  "available", "rental",
     "Toulouse", "31000", 1,  80.0, Decimal("1500"),   False, 35,  5),

    # ── MARSEILLE ──────────────────────────────────────────────────────────────
    ("PROP-MRS-001", "apartment", "T3",      "available", "sale",
     "Marseille", "13008", 3,  80.0, Decimal("380000"), False, 50,  4),
    ("PROP-MRS-002", "apartment", "T2",      "available", "rental",
     "Marseille", "13001", 2,  50.0, Decimal("820"),    False, 30,  4),
    ("PROP-MRS-003", "apartment", "T4",      "available", "sale",
     "Marseille", "13008", 4, 105.0, Decimal("620000"), True,  80,  4),
    ("PROP-MRS-004", "studio",    None,      "available", "sale",
     "Marseille", "13002", 1,  25.0, Decimal("118000"), False, 12,  4),
    ("PROP-MRS-005", "house",     None,      "sold",      "sale",
     "Marseille", "13009", 5, 150.0, Decimal("780000"), False, 220, 4),

    # ── NANTES ─────────────────────────────────────────────────────────────────
    ("PROP-NAN-001", "apartment", "T3",      "available", "sale",
     "Nantes", "44000", 3,  74.0, Decimal("320000"), False, 42,  6),
    ("PROP-NAN-002", "apartment", "T2",      "available", "rental",
     "Nantes", "44000", 2,  47.0, Decimal("760"),    False, 20,  6),
    ("PROP-NAN-003", "studio",    None,      "available", "sale",
     "Nantes", "44300", 1,  22.0, Decimal("130000"), False, 14,  6),
    ("PROP-NAN-004", "house",     None,      "available", "sale",
     "Nantes", "44200", 4, 118.0, Decimal("445000"), False, 65,  6),

    # ── VINCENNES (~6 km E de Paris) ───────────────────────────────────────────
    ("PROP-VIN-001", "apartment", "T3",      "available", "sale",
     "Vincennes", "94300", 3,  75.0, Decimal("480000"), False, 38,  0),
    ("PROP-VIN-002", "apartment", "T2",      "available", "rental",
     "Vincennes", "94300", 2,  45.0, Decimal("1200"),   False, 22,  0),

    # ── NEUILLY-SUR-SEINE (~7 km W de Paris) ───────────────────────────────────
    ("PROP-NEU-001", "apartment", "T4",      "available", "sale",
     "Neuilly-sur-Seine", "92200", 4,  95.0, Decimal("950000"), True,  55,  8),
    ("PROP-NEU-002", "studio",    None,      "available", "sale",
     "Neuilly-sur-Seine", "92200", 1,  25.0, Decimal("285000"), False, 18,  8),

    # ── LEVALLOIS-PERRET (~8 km NW de Paris) ───────────────────────────────────
    ("PROP-LEV-001", "apartment", "T3",      "available", "sale",
     "Levallois-Perret", "92300", 3,  70.0, Decimal("580000"), False, 45,  8),
    ("PROP-LEV-002", "apartment", "T2",      "available", "rental",
     "Levallois-Perret", "92300", 2,  48.0, Decimal("1400"),   False, 15,  8),

    # ── MONTREUIL (~8 km E de Paris) ───────────────────────────────────────────
    ("PROP-MON-001", "apartment", "T3",      "available", "sale",
     "Montreuil", "93100", 3,  68.0, Decimal("390000"), False, 50,  9),
    ("PROP-MON-002", "house",     None,      "available", "sale",
     "Montreuil", "93100", 4, 110.0, Decimal("620000"), False, 70,  9),

    # ── VILLEURBANNE (~4 km E de Lyon) ─────────────────────────────────────────
    ("PROP-VIL-001", "apartment", "T3",      "available", "sale",
     "Villeurbanne", "69100", 3,  73.0, Decimal("320000"), False, 42,  1),
    ("PROP-VIL-002", "apartment", "T2",      "available", "rental",
     "Villeurbanne", "69100", 2,  44.0, Decimal("800"),    False, 25,  1),
    ("PROP-VIL-003", "studio",    None,      "available", "sale",
     "Villeurbanne", "69100", 1,  24.0, Decimal("138000"), False, 12,  1),

    # ── CALUIRE-ET-CUIRE (~5 km N de Lyon) ─────────────────────────────────────
    ("PROP-CAL-001", "house",     None,      "available", "sale",
     "Caluire-et-Cuire", "69300", 5, 145.0, Decimal("750000"), True,  80,  1),
    ("PROP-CAL-002", "apartment", "T3",      "available", "sale",
     "Caluire-et-Cuire", "69300", 3,  72.0, Decimal("380000"), False, 35,  1),

    # ── ALLAUCH (~10 km NE de Marseille) ───────────────────────────────────────
    ("PROP-ALL-001", "house",     None,      "available", "sale",
     "Allauch", "13190", 5, 130.0, Decimal("520000"), False, 60,  4),
    ("PROP-ALL-002", "apartment", "T3",      "available", "sale",
     "Allauch", "13190", 3,  74.0, Decimal("310000"), False, 30,  4),

    # ── PLAN-DE-CUQUES (~9 km NE de Marseille) ─────────────────────────────────
    ("PROP-PDC-001", "house",     None,      "available", "sale",
     "Plan-de-Cuques", "13380", 4, 115.0, Decimal("450000"), False, 48,  4),
    ("PROP-PDC-002", "apartment", "T2",      "available", "rental",
     "Plan-de-Cuques", "13380", 2,  48.0, Decimal("880"),    False, 20,  4),

    # ── MÉRIGNAC (~5 km W de Bordeaux) ─────────────────────────────────────────
    ("PROP-MER-001", "apartment", "T3",      "available", "sale",
     "Mérignac", "33700", 3,  70.0, Decimal("350000"), False, 40,  2),
    ("PROP-MER-002", "house",     None,      "available", "sale",
     "Mérignac", "33700", 4, 112.0, Decimal("420000"), False, 55,  2),

    # ── PESSAC (~6 km SW de Bordeaux) ──────────────────────────────────────────
    ("PROP-PES-001", "apartment", "T2",      "available", "sale",
     "Pessac", "33600", 2,  48.0, Decimal("245000"), False, 28,  2),
    ("PROP-PES-002", "house",     None,      "available", "sale",
     "Pessac", "33600", 5, 128.0, Decimal("475000"), False, 65,  2),

    # ── BLAGNAC (~5 km NW de Toulouse) ─────────────────────────────────────────
    ("PROP-BLG-001", "apartment", "T3",      "available", "sale",
     "Blagnac", "31700", 3,  72.0, Decimal("280000"), False, 35,  5),
    ("PROP-BLG-002", "apartment", "T2",      "available", "rental",
     "Blagnac", "31700", 2,  46.0, Decimal("760"),    False, 18,  5),

    # ── COLOMIERS (~8 km W de Toulouse) ────────────────────────────────────────
    ("PROP-COL-001", "house",     None,      "available", "sale",
     "Colomiers", "31770", 4, 110.0, Decimal("350000"), False, 50,  5),
    ("PROP-COL-002", "apartment", "T3",      "available", "sale",
     "Colomiers", "31770", 3,  68.0, Decimal("258000"), False, 30,  5),

    # ── SAINT-HERBLAIN (~4 km W de Nantes) ─────────────────────────────────────
    ("PROP-SHB-001", "apartment", "T3",      "available", "sale",
     "Saint-Herblain", "44800", 3,  72.0, Decimal("295000"), False, 38,  6),
    ("PROP-SHB-002", "house",     None,      "available", "sale",
     "Saint-Herblain", "44800", 4, 115.0, Decimal("385000"), False, 55,  6),

    # ── REZÉ (~5 km S de Nantes) ────────────────────────────────────────────────
    ("PROP-REZ-001", "apartment", "T2",      "available", "sale",
     "Rezé", "44400", 2,  45.0, Decimal("210000"), False, 22,  6),
    ("PROP-REZ-002", "apartment", "T3",      "available", "rental",
     "Rezé", "44400", 3,  68.0, Decimal("850"),    False, 15,  6),

    # ── CESSON-SÉVIGNÉ (~5 km E de Rennes) ─────────────────────────────────────
    ("PROP-CES-001", "house",     None,      "available", "sale",
     "Cesson-Sévigné", "35510", 5, 135.0, Decimal("450000"), False, 60,  3),
    ("PROP-CES-002", "apartment", "T3",      "available", "sale",
     "Cesson-Sévigné", "35510", 3,  74.0, Decimal("280000"), False, 28,  3),
]


def make_property(row: tuple, agents: list[Agent]) -> Property:
    (uid, ptype, sub_type, status, txtype,
     city, postal, rooms, surface, price,
     prestige, created_days, agent_idx) = row

    return Property(
        uid=uid,
        type=ptype,
        sub_type=sub_type,
        status=status,
        transaction_type=txtype,
        city=city,
        postal_code=postal,
        latitude=CITY_COORDS.get(city, (None, None))[0],
        longitude=CITY_COORDS.get(city, (None, None))[1],
        country="FR",
        rooms_count=rooms,
        surface_area=surface,
        mandate_price=price,
        is_prestige=prestige,
        created_at=days_ago(created_days),
        advisor_id=agents[agent_idx].id,
    )


# ─── DESCRIPTIONS ─────────────────────────────────────────────────────────────
# Textes réalistes anonymisés, un par bien, locale="fr"

DESCRIPTIONS: dict[str, str] = {
    "PROP-PAR-001": (
        "Appartement T2 traversant au 4ème étage avec ascenseur. Séjour lumineux "
        "donnant sur cour arborée, cuisine séparée équipée, chambre avec placards, "
        "salle de bain, WC indépendants. Cave en sous-sol."
    ),
    "PROP-PAR-002": (
        "Bel appartement T3 haussmannien entièrement rénové. Parquet en chêne, "
        "moulures conservées, double salon, cuisine ouverte équipée, deux chambres "
        "dont une suite parentale, salle de bain avec baignoire, WC séparés. "
        "Gardien. Prestations de standing."
    ),
    "PROP-PAR-003": (
        "Appartement T4 au 2ème étage. Hall d'entrée, vaste séjour, cuisine ouverte "
        "aménagée, trois chambres dont une avec dressing, salle de bain, "
        "salle d'eau, deux WC. Bon état général, cave et parking en sous-sol."
    ),
    "PROP-PAR-004": (
        "Appartement T2 au 3ème étage sans ascenseur. Séjour avec coin cuisine, "
        "chambre, salle d'eau, WC. Parquet bois, double vitrage. Idéal investisseur "
        "ou premier achat locatif."
    ),
    "PROP-PAR-005": (
        "Studio de 22 m² au 5ème étage avec vue dégagée. Pièce principale avec coin "
        "cuisine aménagée, salle de bain avec WC. Très lumineux, exposition plein "
        "sud. Copropriété bien tenue."
    ),
    "PROP-PAR-006": (
        "Studio fonctionnel au 1er étage. Pièce principale avec cuisine ouverte, "
        "salle d'eau, WC. Proche métro et commerces. Disponible immédiatement."
    ),
    "PROP-PAR-007": (
        "Maison de ville sur trois niveaux. Rez-de-chaussée : salon-séjour, "
        "cuisine ouverte. 1er étage : trois chambres, salle de bain. 2ème étage : "
        "chambre parentale en suite, terrasse de 18 m². Jardin privatif 60 m²."
    ),
    "PROP-PAR-008": (
        "Place de parking sécurisée en sous-sol, accès par interphone. "
        "Dimensions 2,50 m × 5,00 m. Idéal pour véhicule compacte ou berline."
    ),
    "PROP-LYO-001": (
        "Appartement T3 au 3ème étage avec balcon filant. Entrée, séjour lumineux, "
        "cuisine équipée ouverte, deux chambres, salle de bain, WC séparés. "
        "Double vitrage. Cave. Proche Part-Dieu."
    ),
    "PROP-LYO-002": (
        "T2 en rez-de-jardin avec terrasse privative de 15 m². Séjour, cuisine "
        "ouverte, chambre, salle d'eau. Parking privatif. Résidence calme."
    ),
    "PROP-LYO-003": (
        "Studio traversant 7ème arrondissement. Pièce principale bien agencée, "
        "cuisine américaine, salle de bain. Au calme sur cour. Charges réduites."
    ),
    "PROP-LYO-004": (
        "Maison familiale 140 m² sur terrain de 380 m². Cuisine ouverte sur salon, "
        "salle à manger, 4 chambres, 2 salles de bain, garage double. "
        "Quartier résidentiel, écoles à pied."
    ),
    "PROP-LYO-005": (
        "Local commercial de 55 m² en rez-de-chaussée, vitrine sur rue passante. "
        "Arrière-boutique, WC indépendant, cave de stockage. "
        "Idéal commerce alimentaire ou services de proximité."
    ),
    "PROP-BDX-001": (
        "Appartement T3 chartrons, immeuble pierre de taille, 2ème étage. "
        "Séjour double, cuisine équipée, deux chambres, salle de bain, WC. "
        "Parquet ancien, cheminées décoratives. Quartier très recherché."
    ),
    "PROP-BDX-002": (
        "T2 lumineux au 4ème étage avec ascenseur. Séjour donnant sur boulevard, "
        "cuisine ouverte aménagée, chambre, salle d'eau, WC. "
        "Proche tramway. Disponible de suite."
    ),
    "PROP-BDX-003": (
        "Grand T4 en duplex, immeuble années 80 avec gardien. Séjour avec balcon, "
        "cuisine indépendante, 3 chambres, salle de bain, salle d'eau. "
        "Cave et parking. Secteur Mérignac."
    ),
    "PROP-BDX-004": (
        "Studio neuf, résidence avec interphone et digicode. Pièce principale 24 m², "
        "kitchenette aménagée, salle de bain avec WC. Parquet flottant, "
        "isolation phonique renforcée."
    ),
    "PROP-BDX-005": (
        "Maison contemporaine 115 m² sur terrain 320 m². Rez-de-chaussée : "
        "cuisine ouverte, salon-séjour, chambre PMR, salle d'eau. 1er étage : "
        "3 chambres, salle de bain, WC. Carport double. Proche rocade."
    ),
    "PROP-REN-001": (
        "T3 traversant au 2ème étage, immeuble Pierre. Entrée, séjour avec "
        "parquet, cuisine équipée, 2 chambres, salle de bain, WC séparés. "
        "Cave. Quartier Thabor."
    ),
    "PROP-REN-002": (
        "Appartement T2 refait à neuf. Séjour lumineux, cuisine ouverte équipée, "
        "chambre, salle d'eau, WC. Double vitrage PVC. "
        "Proche gare et commerces. Disponible immédiatement."
    ),
    "PROP-REN-003": (
        "Studio rénové 20 m², quartier République. Cuisine ouverte, salle d'eau, "
        "WC. Parquet. Immeuble avec interphone. Idéal étudiant ou jeune actif."
    ),
    "PROP-REN-004": (
        "Studio meublé et équipé, 4ème étage. Coin cuisine, salle d'eau WC. "
        "Accès fibre optique. Charges comprises : eau froide, chauffage collectif. "
        "Idéal mobilité professionnelle."
    ),
    "PROP-REN-005": (
        "Belle maison 128 m² sur terrain 500 m². Entrée, salon, salle à manger, "
        "cuisine équipée indépendante, 4 chambres, salle de bain, salle d'eau, "
        "WC. Garage, terrasse, jardin clos. Proche rocade nord."
    ),
    "PROP-LHA-001": (
        "Appartement T2, résidence récente proche du Volcan. Séjour ouvert sur "
        "cuisine, chambre, salle d'eau, WC. Balcon 8 m², cave, parking extérieur. "
        "Bon état général."
    ),
    "PROP-LHA-002": (
        "T3 familial au 1er étage avec terrasse de 20 m². Salon-séjour, cuisine "
        "séparée, deux chambres, salle de bain, WC. Parking. "
        "Quartier résidentiel proche lycée."
    ),
    "PROP-LHA-003": (
        "Studio port de commerce, vue mer partielle du 6ème étage. "
        "Pièce principale, coin cuisine, salle de bain WC. "
        "Copropriété sécurisée avec digicode."
    ),
    "PROP-LHA-004": (
        "Maison de plain-pied 105 m² sur terrain 600 m². Entrée, séjour, "
        "cuisine aménagée, 3 chambres dont une parentale avec salle d'eau privée, "
        "salle de bain, WC. Garage, abri de jardin."
    ),
    "PROP-BOU-001": (
        "Appartement T3 rénové, immeuble années 30, 3ème étage avec ascenseur. "
        "Hall d'entrée, grand séjour, cuisine ouverte sur mesure, 2 chambres, "
        "salle de bain, WC. Gardien. Cave. Secteur Point du Jour."
    ),
    "PROP-BOU-002": (
        "T2 moderne au 6ème étage avec vue dégagée. Salon avec cuisine ouverte "
        "haut de gamme, chambre avec dressing, salle de bain, WC. "
        "Balcon 6 m², cave. Proche métro ligne 10."
    ),
    "PROP-BOU-003": (
        "Appartement T4 familial, duplex sur deux niveaux. Salon-séjour 45 m², "
        "cuisine équipée, 3 chambres dont une suite parentale, 2 salles de bain. "
        "Terrasse 30 m², box fermé. Résidence gardiennée."
    ),
    "PROP-BOU-004": (
        "Studio 28 m² idéalement situé, 2ème étage. Pièce principale, cuisine "
        "aménagée, salle de bain, WC. Parquet point de Hongrie, fenêtres sur cour. "
        "DPE C."
    ),
    "PROP-BOU-005": (
        "Villa d'architecte 180 m² sur terrain 450 m², quartier résidentiel. "
        "Rez-de-chaussée : séjour double hauteur 60 m², cuisine ouverte avec îlot, "
        "chambre d'amis. 1er étage : 4 suites parentales. Piscine, double garage. "
        "Prestations premium."
    ),
    "PROP-SDN-001": (
        "Appartement T3 au 4ème étage, résidence récente. Séjour avec balcon, "
        "cuisine équipée, 2 chambres, salle de bain, WC. Cave et parking inclus. "
        "À 5 min du RER D."
    ),
    "PROP-SDN-002": (
        "T2 en rez-de-chaussée surélevé. Séjour, cuisine ouverte, chambre, "
        "salle d'eau. Cour privative 12 m². Idéal investissement locatif, "
        "secteur en pleine rénovation urbaine."
    ),
    "PROP-SDN-003": (
        "Studio 19 m² proche basilique. Cuisine ouverte, salle d'eau WC. "
        "Chauffage individuel électrique. Charges très faibles. "
        "Convient profil étudiant ou premier investisseur."
    ),
    "PROP-SDN-004": (
        "Maison de ville en bande, 92 m², 3 niveaux. Séjour, cuisine, "
        "3 chambres, salle de bain, WC. Jardin de 80 m². "
        "Travaux de rafraîchissement à prévoir. Prix net vendeur."
    ),
    "PROP-TLS-001": (
        "T3 avec terrasse de 10 m², 2ème étage avec ascenseur. Séjour ouvert sur "
        "cuisine équipée, 2 chambres, salle de bain, WC. Cave. "
        "Proche métro ligne B, résidence sécurisée."
    ),
    "PROP-TLS-002": (
        "Appartement T2 côté Capitole. Séjour lumineux, cuisine indépendante, "
        "chambre, salle de bain. 3ème étage sans ascenseur, immeuble ancien. "
        "Loué en meublé. Bon rendement locatif."
    ),
    "PROP-TLS-003": (
        "Studio étudiant 23 m² proche campus Jean-Jaurès. Cuisine ouverte, "
        "salle de bain WC. Parquet, interphone vidéo. "
        "Très bon état. Disponible à la rentrée."
    ),
    "PROP-TLS-004": (
        "Maison de caractère 132 m² sur terrain 420 m², quartier Lardenne. "
        "Cuisine ouverte haut de gamme, salon-séjour, 4 chambres, "
        "2 salles de bain. Garage, piscine hors-sol, pergola."
    ),
    "PROP-TLS-005": (
        "Bureau de 80 m² à louer en rez-de-chaussée, vitrine sur rue. "
        "Open space modulable, kitchenette, sanitaires privatifs. "
        "Fibre incluse. Idéal cabinet libéral ou agence."
    ),
    "PROP-MRS-001": (
        "T3 traversant 8ème arrondissement, résidence avec gardien. Séjour, "
        "cuisine équipée, 2 chambres, salle de bain, WC. "
        "Loggia 6 m² côté parc, cave et parking en sous-sol."
    ),
    "PROP-MRS-002": (
        "Appartement T2 proche Vieux-Port. 2ème étage, séjour avec vue mer, "
        "cuisine, chambre, salle d'eau. Immeuble pierre, charme de l'ancien. "
        "Idéal location saisonnière ou résidence principale."
    ),
    "PROP-MRS-003": (
        "Grand T4 prestige, immeuble récent résidence fermée. Entrée, double "
        "séjour, cuisine ouverte îlot central, 3 chambres dont suite parentale, "
        "2 salles de bain. Terrasse 25 m², double parking. Prestations haut de gamme."
    ),
    "PROP-MRS-004": (
        "Studio centre-ville, 2ème étage. Pièce principale avec coin cuisine, "
        "salle de bain WC. Lumineux sur cour calme. "
        "DPE D. Charges de copropriété modérées."
    ),
    "PROP-MRS-005": (
        "Villa provençale 150 m² sur terrain 800 m², piscine. Séjour de 50 m² "
        "avec cheminée, cuisine provençale, 4 chambres, 2 salles de bain. "
        "Double garage, pool house, vue dégagée collines."
    ),
    "PROP-NAN-001": (
        "Appartement T3 île de Nantes, immeuble contemporain. Séjour ouvert "
        "sur balcon, cuisine équipée, 2 chambres, salle de bain, WC. "
        "Cave et parking. Proche tramway ligne 1."
    ),
    "PROP-NAN-002": (
        "T2 quartier Chantenay, vue sur Loire. 3ème étage, séjour-cuisine ouverte, "
        "chambre, salle d'eau. Parquet, fenêtres double vitrage. "
        "Proximité commerces et transport."
    ),
    "PROP-NAN-003": (
        "Studio rénové quartier Bouffay, cœur de ville. 22 m², cuisine ouverte, "
        "salle de bain WC. Parquet neuf, peintures fraîches. "
        "Idéal étudiant ou investisseur."
    ),
    "PROP-NAN-004": (
        "Maison 118 m² sur terrain 350 m², quartier Saint-Sébastien. "
        "Salon-séjour, cuisine aménagée, 4 chambres dont une de plain-pied, "
        "salle de bain, salle d'eau. Terrasse, garage, jardin clos."
    ),

    # ── Communes proches de Paris ──────────────────────────────────────────────
    "PROP-VIN-001": (
        "Appartement T3 traversant au 2ème étage, résidence calme proche bois de "
        "Vincennes. Séjour lumineux, cuisine équipée, deux chambres, salle de bain, "
        "WC séparés. Cave. Idéal famille, écoles à pied."
    ),
    "PROP-VIN-002": (
        "T2 au 3ème étage avec ascenseur. Séjour-cuisine ouverte, chambre, "
        "salle d'eau. Proche RER A et commerces du centre-ville. "
        "Disponible immédiatement. Bon état général."
    ),
    "PROP-NEU-001": (
        "Grand T4 prestige, 2ème étage avec ascenseur, gardien. Hall d'entrée "
        "marbré, double séjour, cuisine équipée haut de gamme, 3 chambres dont "
        "suite parentale, 2 salles de bain. Cave et parking. Prestations premium."
    ),
    "PROP-NEU-002": (
        "Studio 25 m² au 4ème étage avec vue dégagée. Pièce principale bien "
        "agencée, kitchenette aménagée, salle de bain WC. Parquet, double vitrage. "
        "Proche métro ligne 1. Copropriété bien tenue."
    ),
    "PROP-LEV-001": (
        "Appartement T3 rénové, 5ème étage avec ascenseur. Séjour avec balcon, "
        "cuisine ouverte équipée, 2 chambres, salle de bain, WC. "
        "Proche métro Anatole France. Cave incluse."
    ),
    "PROP-LEV-002": (
        "T2 moderne au 2ème étage. Séjour lumineux sur rue piétonne, cuisine "
        "aménagée, chambre, salle d'eau. Idéal jeune actif ou investisseur. "
        "Loyer charges comprises négociable."
    ),
    "PROP-MON-001": (
        "Appartement T3 quartier Croix de Chavaux, immeuble années 70 refait. "
        "Entrée, séjour, cuisine indépendante, 2 chambres, salle de bain, WC. "
        "Cave. Proche métro ligne 9. Bon rapport qualité-prix."
    ),
    "PROP-MON-002": (
        "Maison de ville 110 m² sur 3 niveaux, quartier résidentiel. "
        "Salon-séjour, cuisine ouverte, 3 chambres, salle de bain, salle d'eau. "
        "Jardin de 80 m², parking privatif. Proche commerces et transport."
    ),

    # ── Communes proches de Lyon ────────────────────────────────────────────────
    "PROP-VIL-001": (
        "T3 traversant 3ème étage avec balcon. Séjour lumineux, cuisine équipée "
        "ouverte, 2 chambres, salle de bain, WC séparés. Proche tram T3 et "
        "universités. Cave. Idéal famille ou investisseur."
    ),
    "PROP-VIL-002": (
        "Appartement T2 en rez-de-jardin avec terrasse privative. Séjour, "
        "cuisine ouverte, chambre, salle d'eau. Résidence calme avec parking. "
        "Proche campus La Doua."
    ),
    "PROP-VIL-003": (
        "Studio 24 m² quartier Gratte-Ciel, entièrement rénové. Cuisine ouverte "
        "équipée, salle de bain WC. Parquet, peintures fraîches. "
        "Proche tram et commerces. Idéal étudiant."
    ),
    "PROP-CAL-001": (
        "Villa prestige 145 m² sur terrain 600 m², vue panoramique sur Lyon. "
        "Grand séjour avec cheminée, cuisine professionnelle, 4 chambres dont "
        "suite parentale, 2 salles de bain. Piscine, double garage."
    ),
    "PROP-CAL-002": (
        "Appartement T3, 2ème étage, immeuble années 60 bien entretenu. "
        "Séjour avec loggia, cuisine séparée équipée, 2 chambres, salle de bain. "
        "Calme résidentiel. Vue collines. Cave et parking."
    ),

    # ── Communes proches de Marseille ───────────────────────────────────────────
    "PROP-ALL-001": (
        "Maison provençale 130 m² sur terrain 800 m², village d'Allauch. "
        "Séjour lumineux avec cheminée, cuisine équipée, 4 chambres, "
        "2 salles de bain. Terrasse, piscine, garage. Vue collines."
    ),
    "PROP-ALL-002": (
        "Appartement T3 résidence récente, 3ème étage avec ascenseur. "
        "Séjour ouvert sur terrasse de 15 m², cuisine équipée, 2 chambres, "
        "salle de bain, WC. Parking et cave inclus. Calme garanti."
    ),
    "PROP-PDC-001": (
        "Maison individuelle 115 m² sur terrain 450 m², quartier résidentiel. "
        "Rez-de-chaussée : séjour, cuisine ouverte, chambre. 1er étage : "
        "3 chambres, salle de bain. Garage, terrasse, jardin. DPE C."
    ),
    "PROP-PDC-002": (
        "T2 lumineux au 1er étage, résidence avec gardien. Séjour avec balcon, "
        "cuisine aménagée, chambre, salle d'eau. Proche bus ligne 30. "
        "Disponible de suite. Idéal investisseur."
    ),

    # ── Communes proches de Bordeaux ────────────────────────────────────────────
    "PROP-MER-001": (
        "Appartement T3 résidence des années 2000, 2ème étage. Séjour avec "
        "terrasse de 10 m², cuisine ouverte, 2 chambres, salle de bain. "
        "Proche aéroport et rocade. Cave et parking inclus."
    ),
    "PROP-MER-002": (
        "Maison contemporaine 112 m² sur terrain 380 m². Cuisine ouverte sur "
        "salon, 3 chambres, salle de bain, salle d'eau. Garage, terrasse. "
        "Quartier résidentiel proche commerces."
    ),
    "PROP-PES-001": (
        "Appartement T2 quartier Saige, immeuble récent avec ascenseur. "
        "Séjour lumineux, cuisine ouverte, chambre, salle d'eau, WC. "
        "Balcon, cave. Proche tram B et université de Bordeaux."
    ),
    "PROP-PES-002": (
        "Belle maison 128 m² sur terrain 500 m², quartier résidentiel. "
        "Salon-séjour, cuisine aménagée indépendante, 4 chambres, 2 salles de "
        "bain. Garage, piscine hors-sol. Proche rocade et commerces."
    ),

    # ── Communes proches de Toulouse ────────────────────────────────────────────
    "PROP-BLG-001": (
        "Appartement T3, 3ème étage avec ascenseur, résidence récente sécurisée. "
        "Séjour avec balcon, cuisine équipée, 2 chambres, salle de bain, WC. "
        "Cave et parking. Proche Airbus et tramway T1."
    ),
    "PROP-BLG-002": (
        "T2 lumineux au 2ème étage. Séjour-cuisine ouverte, chambre, salle d'eau. "
        "Balcon 5 m². Proche zone Aéroconstellation. "
        "Idéal profil ingénieur ou mobilité pro."
    ),
    "PROP-COL-001": (
        "Maison de plain-pied 110 m² sur terrain 420 m². Séjour ouvert sur "
        "cuisine, 3 chambres dont une parentale en suite, salle de bain. "
        "Garage, terrasse, jardin clos. Quartier pavillonnaire calme."
    ),
    "PROP-COL-002": (
        "Appartement T3 au 4ème étage, résidence années 90. Séjour avec vue "
        "dégagée, cuisine indépendante, 2 chambres, salle de bain. "
        "Cave. Proche bus Linéo 1 vers Toulouse."
    ),

    # ── Communes proches de Nantes ───────────────────────────────────────────────
    "PROP-SHB-001": (
        "T3 au 1er étage, immeuble récent basse consommation. Séjour ouvert "
        "sur balcon, cuisine équipée, 2 chambres, salle de bain, WC. "
        "Cave et parking. Proche tramway ligne 3."
    ),
    "PROP-SHB-002": (
        "Maison 115 m² sur terrain 400 m², quartier pavillonnaire. "
        "Salon-séjour, cuisine ouverte, 3 chambres, salle de bain, salle d'eau. "
        "Garage, terrasse couverte, jardin. DPE B."
    ),
    "PROP-REZ-001": (
        "Appartement T2 au 3ème étage avec ascenseur, vue sur Loire. Séjour "
        "lumineux, cuisine ouverte, chambre, salle d'eau. Cave incluse. "
        "Proche tramway ligne 2 et commerces du centre."
    ),
    "PROP-REZ-002": (
        "T3 au 2ème étage, résidence calme avec espaces verts. Séjour avec "
        "balcon, cuisine séparée, 2 chambres, salle de bain. Parking. "
        "Disponible de suite."
    ),

    # ── Commune proche de Rennes ────────────────────────────────────────────────
    "PROP-CES-001": (
        "Belle maison 135 m² sur terrain 550 m², quartier résidentiel "
        "Cesson-Sévigné. Entrée, salon-séjour, cuisine équipée, "
        "4 chambres dont une parentale en suite, 2 salles de bain. "
        "Garage double, terrasse, jardin arboré. DPE C."
    ),
    "PROP-CES-002": (
        "Appartement T3 au 2ème étage, résidence récente. Séjour avec balcon "
        "exposé sud, cuisine ouverte équipée, 2 chambres, salle de bain, WC. "
        "Cave et parking. Proche Rennes Atalante et RN157."
    ),
}


# ─── MANDATE ORDER NUMBERS ────────────────────────────────────────────────────

def make_order_number(index: int) -> str:
    return f"MND-2025-{index:05d}"


# ─── SEED FUNCTION ────────────────────────────────────────────────────────────

async def seed() -> None:
    """
    Insère le dataset complet dans une transaction unique.

    Ordre obligatoire (contraintes FK) :
      agents → properties → descriptions + listings → mandates → sales/rentals

    flush() entre chaque couche pour obtenir les PK auto-générées avant
    de construire les objets dépendants.
    """
    async with AsyncSessionLocal() as session:

        # ── 1. AGENTS ─────────────────────────────────────────────────────────
        # session.add_all() ≡ foreach($agents as $a) { $em->persist($a); }
        agents = make_agents()
        session.add_all(agents)

        # flush() = envoie les INSERT, génère les agent.id
        # SANS commit — on reste dans la même transaction
        await session.flush()

        # ── 2. PROPERTIES ─────────────────────────────────────────────────────
        properties = [make_property(row, agents) for row in PROPERTIES_RAW]
        session.add_all(properties)
        await session.flush()  # génère property.id nécessaire pour descriptions + mandates

        # ── 3. DESCRIPTIONS ───────────────────────────────────────────────────
        descriptions = []
        for prop in properties:
            text = DESCRIPTIONS.get(prop.uid)
            if text:
                descriptions.append(Description(
                    property_id=prop.id,
                    locale="fr",
                    description=text,
                ))
        session.add_all(descriptions)

        # ── 4. PROPERTY LISTINGS ──────────────────────────────────────────────
        # ~70 % des biens sont publiés (statut available principalement)
        listings = []
        for prop in properties:
            if prop.status in ("available", "rented"):
                listings.append(PropertyListing(
                    property_id=prop.id,
                    first_publish_date=prop.created_at + timedelta(days=2),
                    last_publish_date=prop.created_at + timedelta(days=3),
                    broadcast_mode="portals" if prop.status == "available" else "agency_only",
                    show_price=prop.transaction_type == "sale",
                ))
        session.add_all(listings)

        # ── 5. MANDATES ───────────────────────────────────────────────────────
        mandates = []
        for i, prop in enumerate(properties):
            is_exclusive = (i % 3 == 0)  # un tiers en exclusivité
            validated = prop.created_at + timedelta(days=1)
            mandate = Mandate(
                order_number=make_order_number(i + 1),
                property_id=prop.id,
                agent_id=prop.advisor_id,
                validated_at=validated,
                property_city=prop.city,
                property_surface=prop.surface_area,
                property_designation=f"{prop.type.capitalize()} {prop.city}",
                exclusivity_terminated_at=(
                    validated + timedelta(days=90) if is_exclusive else None
                ),
            )
            mandates.append(mandate)

        session.add_all(mandates)
        await session.flush()  # génère mandate.mandate_id

        # ── 6. MANDATE SALES / RENTALS ────────────────────────────────────────
        sales = []
        rentals = []

        for mandate, prop in zip(mandates, properties):
            is_exclusive = mandate.exclusivity_terminated_at is not None
            mandate_type = "exclusive" if is_exclusive else "simple"

            if prop.transaction_type == "sale":
                price = prop.mandate_price or Decimal("0")
                net = (price * Decimal("0.963")).quantize(Decimal("0.01"))
                # Quelques biens montrent une négociation (prix effectif réduit)
                negotiated = prop.status == "sold"
                eff_price = (price * Decimal("0.975")).quantize(Decimal("0.01")) if negotiated else price
                eff_net   = (net   * Decimal("0.975")).quantize(Decimal("0.01")) if negotiated else net

                sales.append(MandateSale(
                    mandate_id=mandate.mandate_id,
                    type=mandate_type,
                    pricing_price=price,
                    pricing_netprice=net,
                    effectivepricing_price=eff_price,
                    effectivepricing_netprice=eff_net,
                    effectivepricing_changedat=days_ago(15) if negotiated else None,
                ))

            else:  # rental
                rent = prop.mandate_price or Decimal("0")
                charges = Decimal("80") if rent < Decimal("1000") else Decimal("150")
                deposit = (rent * Decimal("2")).quantize(Decimal("0.01"))
                is_furnished = prop.uid.endswith("004") or prop.uid.endswith("006")

                rentals.append(MandateRental(
                    mandate_id=mandate.mandate_id,
                    type=mandate_type,
                    rental_type="furnished" if is_furnished else "unfurnished",
                    lease_duration=12 if is_furnished else 36,
                    availability_at=days_ago(-7),  # disponible dans 7 jours
                    rent_net=rent,
                    rent_charges=charges,
                    security_deposit=deposit,
                    payment_frequency="monthly",
                    effectivepricing_net=rent,
                    effectivepricing_charges=charges,
                ))

        session.add_all(sales)
        session.add_all(rentals)

        # ── 7. COMMIT ─────────────────────────────────────────────────────────
        # Un seul commit pour l'ensemble du dataset → atomique
        # Si une contrainte FK ou UNIQUE échoue, tout est annulé.
        await session.commit()

    # ── Résumé ────────────────────────────────────────────────────────────────
    print("✅ Seed terminé avec succès")
    print(f"   Agents          : {len(agents)}")
    print(f"   Properties      : {len(properties)}")
    print(f"   Descriptions    : {len(descriptions)}")
    print(f"   Listings        : {len(listings)}")
    print(f"   Mandates        : {len(mandates)}")
    print(f"   Mandate sales   : {len(sales)}")
    print(f"   Mandate rentals : {len(rentals)}")


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # asyncio.run() = boucle événementielle unique pour scripts standalone
    # Équivalent : bin/console doctrine:fixtures:load --no-interaction
    asyncio.run(seed())
