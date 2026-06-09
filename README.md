![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Qdrant](https://img.shields.io/badge/Qdrant-vector--db-DC244C?logo=qdrant&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-LLaMA%203.1-F55036)
![Tests](https://img.shields.io/badge/Tests-380%2B-success?logo=pytest&logoColor=white)
![Deployed](https://img.shields.io/badge/Deployed-Live-brightgreen?logo=vercel&logoColor=white)

# Moteur de recherche immobilière par IA

> Un moteur de requêtes en langage naturel pour données immobilières — construit
> de façon incrémentale, couche par couche, de la recherche SQL à la recherche
> sémantique vectorielle.

---

## Table des matières

- [Vision du projet](#-vision-du-projet)
- [Roadmap d'évolution](#roadmap-dévolution)
  - [V1 — Fondation SQL](#v1--fondation-de-la-recherche-sql)
  - [V1.1 — Parsing déterministe](#v11--parsing-déterministe)
  - [V2 — Query Engine](#v2--couche-query-engine)
  - [V2.1 — Hygiène sémantique](#v21--hygiène-sémantique--filtrage-des-tokens-parasites)
  - [V2.2 — Hygiène grammaticale](#v22--hygiène-grammaticale--extension-des-stopwords)
  - [V2.3 — Termes sémantiques composés](#v23--détection-de-termes-sémantiques-composés)
  - [V2.4 — Synonymes & fuzzy matching](#v24--synonymes-et-tolérance-aux-fautes-de-frappe-pré-llm)
  - [V3 — Recherche sémantique](#v3--recherche-sémantique-qdrant)
  - [V4 — Parser LLM à portillon](#v4--parser-dintent-llm-à-portillon-groq-sync)
  - [Recherche de proximité](#recherche-de-proximité-v1--bounding-box-sql--haversine-python)
  - [V5 — Hybride (planifié)](#v5--recherche-hybride-planifiée)
  - [V6 — LLM complet (futur)](#v6--parser-llm-complet-futur)
- [Architecture hexagonale — Ports & Adapters](#-architecture-hexagonale--ports--adapters)
- [Stratégie d'architecture de recherche](#-stratégie-darchitecture-de-recherche--pourquoi-sql-en-premier-)
- [Choix techniques majeurs](#-choix-techniques-majeurs)
- [Stratégie de test](#-stratégie-de-test)
- [Commandes essentielles](#-commandes-essentielles)
- [Structure du projet](#-structure-du-projet)
- [Responsabilités des couches](#-responsabilités-des-couches)
- [Endpoints](#-endpoints)
- [Exemples de requêtes en langage naturel](#-exemples-de-requêtes-en-langage-naturel)
- [Dataset](#-dataset)
- [Variables d'environnement](#-variables-denvironnement)
- [Stratégie de pagination](#stratégie-de-pagination-par-type-de-requête)
- [Frontend](#frontend)
- [Stack technique](#-stack-technique)

---

## Vision du projet

### Pourquoi NLP → Intent JSON → Query Engine ?

La plupart des prototypes de "recherche IA" câblent directement la saisie
utilisateur à une requête SQL ou à un prompt LLM. Ça fonctionne jusqu'à un
certain point : on ne peut pas le tester, on ne peut pas expliquer ses
décisions, et remplacer une couche casse tout le reste.

Ce projet prend l'approche inverse. Chaque requête utilisateur passe par trois
étapes explicites, testables indépendamment :

```
Requête utilisateur (texte libre)
       │
       ▼
  NLP Parser                    ← rule-based aujourd'hui, LLM demain
       │  PropertyIntent (DTO)
       ▼
  QueryResolver                 ← fonction pure, sans I/O, 100% testable
       │  QueryResolution { strategy, reason }
       ▼
  SearchProperty (use case)     ← I/O async, dispatche vers le bon backend
       ├── sql_only    → PostgreSQL (filtres structurés)
       ├── semantic    → embed → Qdrant → hydrate PostgreSQL
       ├── nearby      → bounding box SQL + Haversine Python
       └── hybrid      → pré-filtre SQL + rerank sémantique
```

**Pourquoi pas NLP → SQL direct ?**

| Approche | Testabilité | Évolutivité | Explicabilité |
|---|---|---|---|
| NLP → SQL direct | Difficile (SQL = effet de bord) | Impossible de remplacer le parser | Aucune |
| NLP → Intent → Query Engine | Chaque étape testée unitairement en isolation | Parser remplaçable sans toucher au SQL | Champ `query_resolution` dans chaque réponse API |

Le DTO Pydantic `PropertyIntent` est le contrat stable entre la couche de
compréhension du langage et la couche d'exécution des requêtes. Remplacer le
parser rule-based par un LLM (V6) ne nécessite aucun changement dans les
couches SQL ou Qdrant.

### Objectif final

Un **moteur de recherche hybride** qui :
1. Extrait des filtres structurés depuis le langage naturel (ville, prix, pièces…)
2. Identifie l'intention qualitative ("lumineux", "vue mer", "proche gare")
3. Route vers SQL, la recherche vectorielle, ou les deux — de façon transparente
4. Retourne des résultats classés par pertinence, pas par ordre d'insertion

---

## Roadmap d'évolution

### V1 — Fondation de la recherche SQL

**Ce qui a été construit**

| Fichier | Rôle |
|---|---|
| `entities/nlp/intent_schema.py` | DTO Pydantic `PropertyIntent` — le contrat stable |
| `entities/nlp/intent_parser.py` | Parser rule-based : normaliser → correspondance de mots-clés → regex |
| `adapters/gateways/db/repositories/property_repository.py` | Constructeur de requêtes SQLAlchemy depuis un `PropertyIntent` |
| `adapters/controllers/property_search.py` | Endpoint `GET /properties/search?q=` |
| `scripts/seed_database.py` | 50 biens, 10 villes, 10 agents |

**Pourquoi commencer par là ?**

La recherche SQL est déterministe et totalement testable sans infrastructure ML.
Elle établit le squelette architectural — couches Clean Architecture, SQLAlchemy
async, contrats I/O Pydantic — avant d'ajouter de la complexité.

Le parser a été volontairement maintenu simple : normaliser le texte → faire
correspondre des mots-clés → extraire des patterns regex → assembler le DTO.
Chaque extracteur (`_extract_city`, `_extract_max_price`, …) est une fonction
pure avec ses propres tests unitaires.

---

### V1.1 — Parsing Déterministe

**Ce qui a été construit**

- `_tokenize()` extrait comme fonction nommée (DRY)
- `_extract_city()` réécrit pour retourner la **première ville dans l'ordre du
  texte**, et non la première ville rencontrée lors d'une itération sur un set

**Pourquoi c'est important**

Le `set` Python est non ordonné. Une requête comme `"Paris ou Lyon"` pourrait
retourner `Lyon` avant `Paris` selon la randomisation interne du hachage Python.
Le correctif collecte toutes les correspondances de villes avec leur position
dans le texte et retourne celle avec le plus petit `m.start()`. C'est la
différence entre un parser testable et stable, et un parser non déterministe.

---

### V2 — Couche Query Engine

**Ce qui a été construit**

| Fichier | Rôle |
|---|---|
| `entities/search/query_types.py` | Enum `QueryStrategy` + dataclass `QueryResolution` |
| `entities/search/query_resolver.py` | `resolve_query(intent)` — fonction pure, sans I/O |
| `usecases/search_property/search_property_usecase.py` | `SearchProperty.execute()` — use case orchestrateur async |

**Architecture : Strategy Pattern**

```
resolve_query(intent)  →  QueryResolution(strategy=sql_only, reason="...")
                                │
SearchProperty.execute()        │
        ├── sql_only ───────────┘ → PropertyRepository.search()
        ├── semantic             → embed → QdrantRepository.search() → hydrate PG
        ├── nearby               → bbox SQL + Haversine Python
        └── hybrid               → pré-filtre SQL + rerank sémantique cosinus
```

**Pourquoi séparer Resolver et use case ?**

Le Resolver est une fonction pure : étant donné un intent, il retourne une
décision de routage. Pas de base de données, pas de réseau, pas d'effets de
bord. Il est trivialement testable unitairement et sa logique est auditable en
lisant le code.

Le use case `SearchProperty` fait tout l'I/O async. Il fait confiance à la
décision du Resolver et l'exécute. Séparer ces deux responsabilités évite
l'anti-pattern du "constructeur intelligent" où la logique de routage se cache
dans du code I/O.

Le champ `query_resolution` est exposé dans chaque réponse API, rendant les
décisions de routage du moteur transparentes aux appelants — utile pour le
débogage et pour construire des indicateurs UI ("Résultats basés sur des filtres
structurés").

---

### V2.1 — Hygiène sémantique : filtrage des tokens parasites

**Ce qui a été construit**

| Ajout | Filtre |
|---|---|
| `_PRICE_FORMAT_RE` | `500k`, `300K` |
| `_ROOM_FORMAT_RE` | `t10`, `f4` (variantes longues, 3+ chars) |
| `_is_noise_token(token)` | Combine tous les contrôles de bruit structurel |

**Le bug que ça corrige**

`"Maison Paris 500k"` produisait `semantic_terms=["500k"]`, ce qui amenait
`resolve_query` à retourner `hybrid` — déclenchant une `NotImplementedError`.
La cause : `"500k"` fait 4 caractères (len > 3) et n'est pas un digit pur
(`isdigit()` retourne `False`), donc il passait à travers l'ancien filtre.

Après V2.1 : `"Maison Paris 500k"` → `semantic_terms=[]` → `sql_only`. ✓

**Décision de conception : `_is_noise_token` est séparé de `_STOPWORDS`**

Les tokens parasites sont **structurellement** sans signification (ils encodent
un nombre, un comptage de pièces, une abréviation de prix). Les stopwords sont
**grammaticalement** sans signification. Ce sont des concepts différents qui
méritent des filtres différents.

---

### V2.2 — Hygiène grammaticale : extension des stopwords

**Ce qui a été construit**

`_STOPWORDS` étendu de 22 à 40 entrées, organisées en quatre catégories
explicites : articles/déterminants, prépositions/conjonctions, verbes de
recherche/adverbes, et adjectifs génériques hors domaine.

Ajouts clés : `sans`, `mais`, `donc`, `comme`, `aussi`, `dont`, `vers`, `chez`,
`apres`, `avant`, `entre`, `depuis`, `tres`, `non`, `tout`, `tous`, `toute`,
`cette`, `leur`, `leurs`, `meme`.

**Ce qui est préservé**

Les adjectifs du domaine à valeur sémantique réelle ne sont explicitement PAS
dans les stopwords : `lumineux`, `calme`, `moderne`, `standing`, `renove`,
`terrasse`, `jardin`. Ces mots décrivent des qualités de biens et doivent
survivre pour atteindre la recherche vectorielle.

---

### V2.3 — Détection de termes sémantiques composés

**Ce qui a été construit**

| Ajout | Rôle |
|---|---|
| `_COMPOUND_SEMANTIC_PATTERNS` | `dict[tuple[str, ...], str]` — 13 expressions immobilières |
| `_extract_compound_semantic_terms(tokens)` | Détecteur greedy gauche-droite, correspondance la plus longue en premier |
| `_extract_semantic_terms()` refactorisé | Filtre → détecter les composés → fusionner dans l'ordre du texte |

**Le problème**

`"vue mer"` découpé en `["vue", "mer"]` dégrade la qualité de la recherche
sémantique. `"vue"` et `"mer"` sont des mots communs pris individuellement ;
leur combinaison `"vue mer"` est un qualificatif immobilier spécifique à haute
valeur. L'embedding de `"vue mer"` en tant qu'unité est plus précis que deux
tokens indépendants.

**Conception clé : les tokens sont post-filtre**

Les composés sont détectés **après** le filtrage des bruits et des stopwords.
Cela signifie que `"bord de mer"` fonctionne correctement : `"de"` est un
stopword et est retiré, laissant `["bord", "mer"]` qui correspond au pattern
`("bord", "mer") → "bord de mer"`.

**L'ordre du texte est préservé**

`"studio moderne centre ville"` → `["moderne", "centre ville"]`, pas
`["centre ville", "moderne"]`. L'étape de fusion itère les tokens filtrés
dans l'ordre et émet un composé à sa position de début, en sautant ses tokens
intérieurs.

---

### V2.4 — Synonymes et tolérance aux fautes de frappe (pré-LLM)

**Ce qui a été construit**

| Fichier | Rôle |
|---|---|
| `entities/nlp/fuzzy_matching.py` | Levenshtein Python pur + `find_closest_keyword()` |
| `entities/nlp/intent_parser.py` | 6 nouveaux synonymes de type de bien, `_RENTAL_TOKEN_KEYWORDS`, fallback fuzzy dans 2 extracteurs |

**Pipeline de correspondance en trois niveaux**

Chaque token de la requête utilisateur passe par trois étapes, dans l'ordre :

```
Token
  │
  ▼ 1. Correspondance exacte / synonyme    "pavillon" → house    O(1) dict lookup
  │    Si trouvé → retourner immédiatement
  │
  ▼ 2. (déjà couvert par l'étape 1 — les synonymes vivent dans le même dict)
  │
  ▼ 3. Correspondance floue               "vilaa" ≈ "villa"   Levenshtein ≤ 1
       Si correspondance unique → retourner
       Si ambigu (≥ 2) → None
       Si pas de correspondance → None
```

> Analogie PHP : un `ChoiceType` Symfony avec un `NormalizerInterface`
> "indulgent" — si la valeur n'est pas dans la liste exacte, on essaie de la
> corriger avant de retourner `null`.

**Nouveaux synonymes (type de bien)**

| L'utilisateur écrit | Mappé vers |
|---|---|
| `pavillon` | `house` |
| `maisonette` | `house` |
| `residence` | `house` (approximation documentée) |
| `baraque` | `house` (registre familier) |
| `penthouse` | `apartment` |
| `duplex` | `apartment` |

**Nouvelle abréviation (type de transaction)**

`loc` est détecté comme `rental` via correspondance exacte sur le token
uniquement — jamais comme sous-chaîne, car `"loc" ⊂ "local"` (commercial)
serait un faux positif dangereux.

**Pourquoi `max_distance = 1` seulement ?**

La distance 1 couvre exactement une différence de caractère : une lettre
manquante, une lettre en trop, ou une mauvaise lettre. C'est l'erreur de frappe
la plus courante.

La distance 2 commence à générer des faux positifs entre des mots français
courts : `"pas"` → `"parking"` ? `"loi"` → `"loft"` ? À distance 2 le remède
est pire que le mal.

**Conditions d'arrêt**

| Condition | Pourquoi |
|---|---|
| `len(token) <= 2` | `"la"` → `"loft"` doit être impossible |
| Jamais de fuzzy sur les villes | `"pari"` → `"paris"` correspondrait à toute requête contenant "par" |
| Jamais de fuzzy sur les prix / pièces | Géré par regex, pas par lookup de mots-clés — non applicable |
| Correspondances ambiguës → `None` | Mieux vaut rater que deviner |

**Pourquoi pas encore un LLM ?**

| Critère | Rule-based (V2.4) | LLM (V6) |
|---|---|---|
| Coût | Gratuit (CPU pur) | ~$0.01/requête en prod |
| Déterminisme | `assert result == "apartment"` toujours vrai | Non garanti selon la température |
| Testabilité | Tests unitaires simples | Tests probabilistes, non déterministes |
| Débogage | Stack trace → ligne précise | "Pourquoi ce résultat ?" insoluble |
| Couverture | Fautes simples (distance 1) | Fautes complexes, contexte, polysémie |

**Limites de V2.4**

- Fautes complexes (distance ≥ 2) : `"apartemnt"` → `None` (2 lettres manquantes)
- Formes fléchies : `"appartements"` (pluriel) n'est pas dans le dict V1
- Polysémie : `"résidence"` peut désigner un immeuble, mappé `house` par approximation
- Nouvelles villes / synonymes hors liste : hors scope sans extension du dict

Ces cas seront couverts en V4 avec le Gated LLM Intent Parser (Groq, sync, anti-hallucination).

---

### V3 — Recherche sémantique (Qdrant)

**Ce qui a été construit**

| Fichier | Rôle |
|---|---|
| `adapters/gateways/embedding/embedding_adapter.py` | Singleton lazy `SentenceTransformer`, `embed_text()` |
| `adapters/gateways/vector_db/qdrant_store.py` | Clients Qdrant sync/async, `ensure_collection()` |
| `adapters/gateways/vector_db/qdrant_repository.py` | `QdrantRepository.search()` — recherche vectorielle async |
| `scripts/index_properties_to_qdrant.py` | Indexation batch : PostgreSQL → embeddings → Qdrant |
| `usecases/search_property/search_property_usecase.py` | Branche `semantic_only` : embed → Qdrant → hydrate PG |

**Le flow de la recherche sémantique**

```
semantic_terms: ["lumineux", "vue mer"]
       │
       ▼  f"bien immobilier {' '.join(semantic_terms)}"
query_text = "bien immobilier lumineux vue mer"
       │
       ▼  embed_text(query_text)
vector: list[float]  (384 dimensions, normalisé cosinus)
       │
       ▼  AsyncQdrantClient.search(collection="properties", query_vector=…, limit=10)
[ScoredPoint(id=12, score=0.91), ScoredPoint(id=7, score=0.87), …]
       │
       ▼  property_ids = [r.payload["property_id"] for r in results]
       │
       ▼  SELECT * FROM properties WHERE id IN (12, 7, …)
       │
       ▼  props_by_id = {p.id: p for p in result.scalars().all()}
           [props_by_id[pid] for pid in property_ids if pid in props_by_id]
list[Property]  ← ordre de pertinence Qdrant préservé, IDs périmés ignorés silencieusement
```

**Pourquoi le préfixe de domaine `"bien immobilier …"` ?**

`all-MiniLM-L6-v2` est un modèle généraliste. Sans contexte, `"lumineux
terrasse"` peut correspondre à du contenu lifestyle, des blogs de décoration
intérieure ou de la photographie. Préfixer `"bien immobilier"` ancre le vecteur
de requête dans le voisinage immobilier de l'espace d'embeddings, où il sera
comparé aux descriptions de biens indexées avec le même contexte de domaine.

**Pourquoi préserver l'ordre Qdrant après l'hydratation PostgreSQL ?**

`WHERE id IN (12, 7, 31)` en SQL ne préserve pas l'ordre. PostgreSQL est libre
de retourner les lignes dans l'ordre qu'il juge efficace. Après récupération,
le use case reconstruit un dict `{id: Property}` et réordonne selon la liste
classée originale de Qdrant. Les IDs périmés (biens supprimés de PG depuis la
dernière indexation) sont ignorés silencieusement via `if pid in props_by_id`.

---

### V4 — Parser d'intent LLM à portillon (Groq, sync)

**Ce qui a été construit**

| Fichier | Rôle |
|---|---|
| `entities/nlp/llm_intent_schema.py` | DTO Pydantic `LlmIntentResponse` (couche d'entrée, séparée du domaine) |
| `entities/nlp/confidence_gate.py` | `has_possible_typo()` + `should_use_llm()` — logique de portillon |
| `adapters/gateways/llm/groq_adapter.py` | Groq via SDK OpenAI, sync, singleton lazy, mode JSON |
| `entities/nlp/llm_validator.py` | Anti-hallucination : rejette les champs stricts inventés |
| `entities/nlp/intent_merger.py` | La règle gagne sur les champs stricts ; LLM comble les lacunes ; union sémantique |
| `entities/nlp/intent_parser.py` | `parse_intent_using_llm()` — orchestre le pipeline |

**Architecture**

```
parse_intent_using_llm(query)
        │
        ▼  parse_intent(query)            # rule parser V2.4, tourne toujours
        │
        ▼  should_use_llm(intent, query)
        │   ├─ 2 signaux forts (city+type, city+price, type+tx) → False
        │   └─ 1 signal / faute (d=2) / intent inconnu → True
        │
        ├─ False → return rule_intent     # 0 coût LLM
        │
        └─ True → parse_intent_with_llm(query)   # groq_adapter
                       │
                       ▼  validate_llm_response()   # anti-hallucination
                       │
                       ▼  merge_intents()            # règle > LLM sur les champs stricts
                       │
                       ▼  return PropertyIntent
```

**Pourquoi un portillon ?**

Groq est en free tier mais chaque appel API ajoute ~200-400ms de latence. Le
parser rule-based tourne en microsecondes et couvre ~70% des requêtes réelles
(city + property_type). Le portillon garantit que le LLM n'est appelé que
lorsque le parser rule-based est genuinement incertain. C'est le pattern
VoterInterface : chaque voter a un domaine clair, sans chevauchement.

**Pourquoi un seuil à deux signaux ?**

Un seul signal signifie que l'utilisateur a probablement fait une faute ou
utilisé un synonyme inconnu pour le champ manquant. Un signal = confiant dans
ce qu'on a trouvé, incertain sur le reste → le LLM comble le manque. Deux
signaux = la requête est bien structurée → le LLM n'ajouterait que du bruit
à un coût supplémentaire.

**Pourquoi un validator (anti-hallucination) ?**

Les LLMs hallucinent. `city: "Paris"` inventé depuis le contexte quand Paris
n'a jamais été mentionné est pire que `city: null` — cela redirige silencieusement
la recherche de l'utilisateur. Le validator applique la règle : si un champ
strict ne peut pas être ancré dans le texte original (digit pour le prix, token
de ville pour la ville), le champ est rejeté. Les champs souples (property_type,
transaction_type, semantic_terms) sont toujours conservés car la correction de
fautes et l'enrichissement sémantique sont le but même de l'appel LLM.

**Pourquoi un merger et pas simplement retourner la réponse LLM ?**

Le parser rule-based est déterministe et bien testé. Le LLM est probabiliste.
Sur les champs structurés stricts, l'ordre de confiance est : règle > LLM. Le
merger implémente cela : le `city="Paris"` de la règle gagne sur le `city="Lyon"`
du LLM, mais si la règle a `city=None`, la valeur du LLM comble le manque. Les
termes sémantiques utilisent l'union (les deux sources contribuent, sans
duplicats).

**Pourquoi sync (pas async) ?**

La couche NLP est une couche de calcul pur — string en entrée, DTO en sortie.
Elle n'a pas d'I/O propre. La rendre async propagerait `await` à travers
`parse_intent`, `QueryResolver`, le use case et chaque endpoint API, sans
bénéfice architectural. L'appel Groq est le seul I/O, et `openai.OpenAI` (client
sync) le gère sur le thread appelant. Si la latence devient un problème, tout
l'appel `parse_intent_using_llm()` peut être enveloppé dans `asyncio.to_thread()`
au niveau de l'API sans toucher à la pile NLP.

**Choix du modèle Groq**

`llama-3.1-8b-instant` — rapide (400ms p50), free tier, suffisant pour
l'extraction JSON structurée avec `temperature=0` et un validator.
`max_tokens=512` borne la réponse. Mode JSON (`response_format={"type":
"json_object"}`) garantit une sortie parseable.

**Limites V1 (documentées)**

| Limitation | Pourquoi | Correctif en V5 |
|---|---|---|
| Nombres écrits ("cinq cent mille") | Le validator exige `\d` pour prix/pièces | Validator enrichi avec `word2num` |
| Fautes de ville (distance > 1) | Le parser rule-based ne gère que la distance ≤ 1 | Le LLM peut corriger si confidence_score élevé |
| Requêtes multi-villes | Le merger ne conserve qu'une ville | Type d'intent multi-villes dédié |

---

### Recherche de proximité V1 — Bounding box SQL + Haversine Python

**Objectif**

Permettre aux utilisateurs de rechercher des biens près d'une ville, pas
seulement dans une ville précise.

```
"maison proche de Rambouillet"
→ nearby_city="Rambouillet", search_radius_km=15
→ biens à Rambouillet ET communes environnantes dans un rayon de 15 km
```

**Patterns supportés**

| Phrase utilisateur | `nearby_city` | `search_radius_km` |
|---|---|---|
| "proche de Rambouillet" | Rambouillet | 15 (défaut) |
| "à côté de Le Havre" | Le Havre | 15 (défaut) |
| "autour de Lyon" | Lyon | 15 (défaut) |
| "dans un rayon de 30km de Versailles" | Versailles | 30 (explicite) |

**Invariant** : `city` XOR `nearby_city` — jamais les deux en même temps.
Une requête de ville exacte ("maison à Paris") conserve `city="Paris"` et
`nearby_city=None`.

**Architecture : pourquoi bounding box SQL + Haversine Python ?**

PostgreSQL sans PostGIS ne peut pas calculer des distances géographiques
directement. `WHERE distance(lat, lon) <= 15km` n'est pas du SQL standard valide.
Deux approches seraient problématiques prises seules :

- **Full-scan Python** : charger 10 000 biens pour en garder 50 est un gaspillage d'I/O.
- **SQL seul** : pas de fonction de distance sans PostGIS.

L'approche hybride résout cela efficacement :

```
Étape 1 — Bounding box SQL (filtre géographique carré)
    delta_lat = radius / 111          # 1° lat ≈ 111 km
    delta_lon = radius / (111 × cos(lat))

    WHERE lat BETWEEN (center_lat - delta_lat) AND (center_lat + delta_lat)
      AND lon BETWEEN (center_lon - delta_lon) AND (center_lon + delta_lon)

    → Réduit de ~10 000 biens à ~50–200 candidats

Étape 2 — Haversine Python (filtre cercle précis)
    haversine_distance_km(centre, bien) <= radius_km
    → Ne garde que les biens dans le cercle réel (pas le carré)
```

La bounding box est toujours plus grande que le cercle cible (les coins sont à
`radius × √2` du centre), donc il n'y a pas de faux négatifs : tout bien dans
le cercle est garanti d'être dans la bounding box. Le passage Haversine supprime
les coins.

**Séparation logique métier / infrastructure**

La recherche de proximité est découpée en deux fichiers selon leur nature :

| Fichier | Nature | Contenu |
|---|---|---|
| `entities/geography/proximity.py` | Logique pure (math) | `compute_bounding_box()`, `filter_by_distance()` |
| `adapters/gateways/db/repositories/geospatial_repository.py` | Infrastructure SQL | `get_city_center()` — moyenne des coordonnées en base |
| `entities/geography/distance.py` | Logique pure (math) | Formule Haversine |

**Pourquoi pas PostGIS dès le début ?**

PostGIS (`ST_DWithin` + index GiST) est la solution de production pour les
requêtes géographiques. Il permettrait `WHERE ST_DWithin(geom, target_geom,
radius_meters)` directement en SQL, avec un indexage approprié.

Nous avons choisi de ne pas utiliser PostGIS en V1 pour des raisons pédagogiques :
- PostGIS nécessite d'installer une extension PostgreSQL (`CREATE EXTENSION postgis`)
- Cela change le modèle de données (colonnes géométriques PostGIS vs floats lat/lon simples)
- Les colonnes `latitude`/`longitude` Float existantes fonctionnent déjà à notre échelle V1
- Le pattern bounding box + Haversine est une technique bien connue qui vaut la peine d'être comprise

**Limites V1** (documentées, attendues)

| Limitation | Raison | Correctif V2 |
|---|---|---|
| Ne fonctionne que si les biens ont des coordonnées GPS | `latitude`/`longitude` sont nullables — les biens non géocodés sont exclus | Géocoder à l'ingestion |
| Centre de ville approximatif | Calculé comme la moyenne des coordonnées des biens existants, pas le centroïde officiel de la commune | Table de 35 000 communes (INSEE) |
| Ville inconnue retourne vide | Pas de biens dans cette ville → le centre ne peut pas être calculé | La table communes fournit les centroïdes indépendamment de l'inventaire des biens |
| Full-scan partiel | Les candidats de la bounding box sont chargés en mémoire Python | PostGIS `ST_DWithin` + index GiST |

**Roadmap V2** : table communes INSEE (~35 000 lignes avec centroïdes officiels)
+ PostGIS `ST_DWithin` + index spatial GiST.

---

### V5 — Recherche hybride (planifiée)

**Objectif**

Combiner la précision des filtres structurés SQL avec le rappel de la
similarité vectorielle :

1. Pré-filtre SQL : `WHERE city = 'Paris' AND mandate_price < 500000` → ensemble de candidats
2. Rerank sémantique : embed les termes qualitatifs de l'utilisateur, classe les candidats par similarité cosinus
3. Retourne les top-K résultats classés par score sémantique, dans les contraintes structurées

**Pourquoi pas en V1 ?** Nécessite l'infrastructure d'embedding de V3. Le
Strategy Pattern rend l'implémentation additive : ajouter une branche `hybrid`
dans `SearchProperty.execute()`, zéro changement dans le parser ou l'API.

---

### V6 — Parser LLM complet (futur)

**Objectif**

Remplacer entièrement le `intent_parser.py` rule-based par un appel LLM utilisant
Structured Output. Le schéma Pydantic `PropertyIntent` devient le schéma de
sortie du LLM.

```python
# Esquisse V6 — même signature, internals différents
def parse_intent(query: str) -> PropertyIntent:
    return claude.messages.create(
        model="claude-opus-4-7",
        response_schema=PropertyIntent,
        prompt=f"Extraire l'intent de recherche immobilière : {query}",
    )
```

**Pourquoi pas maintenant ?**

L'approche à portillon (V4) donne 70% du bénéfice à 5% du coût. Un remplacement
complet nécessite des évaluations robustes, un budget de latence approuvé, et
une baseline de fallback — que le parser rule-based fournit désormais.

---

## Architecture hexagonale — Ports & Adapters

Ce projet suit une architecture hexagonale (Ports & Adapters / Clean Architecture).
L'objectif : le code métier ne connaît pas l'infrastructure, et l'infrastructure
est interchangeable sans toucher à la logique.

```
┌─────────────────────────────────────────────────────────────────────┐
│  entities/                  Logique métier pure                     │
│  stdlib + pydantic uniquement — pas de SQLAlchemy, Qdrant, HTTP     │
│                                                                     │
│  nlp/          search/        geography/      embeddings/           │
│  intent_parser  query_resolver  proximity       text_builder        │
│  intent_schema  query_types     distance        similarity          │
│  fuzzy_matching pagination    property.py                           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ dépend de
┌──────────────────────────────▼──────────────────────────────────────┐
│  usecases/                  Orchestration applicative               │
│                                                                     │
│  search_property/search_property_usecase.py   ← use case principal │
│  gateway/                                     ← ports (Protocols)  │
│    PropertyRepositoryGateway                                        │
│    VectorRepositoryGateway                                          │
│    EmbeddingGateway                                                 │
│    LlmGateway                                                       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ implémenté par
┌──────────────────────────────▼──────────────────────────────────────┐
│  adapters/                  Implémentations infrastructure          │
│                                                                     │
│  controllers/               ← routers HTTP FastAPI                  │
│  gateways/db/               ← SQLAlchemy ORM + repositories SQL     │
│  gateways/vector_db/        ← client Qdrant async                  │
│  gateways/embedding/        ← SentenceTransformers singleton        │
│  gateways/llm/              ← client Groq via SDK OpenAI            │
└─────────────────────────────────────────────────────────────────────┘
```

### Les ports (interfaces) — `usecases/gateway/`

Les ports sont des `Protocol` Python : ils définissent ce que le use case
*attend* sans dicter comment c'est implémenté.

| Port | Méthode clé | Implémentation actuelle |
|---|---|---|
| `PropertyRepositoryGateway` | `search()`, `count()`, `search_nearby()`, `count_nearby()` | `PropertyRepository` (SQLAlchemy async) |
| `VectorRepositoryGateway` | `search(vector, top_k)` | `QdrantRepository` |
| `EmbeddingGateway` | `embed(text)` | `EmbeddingAdapter` (SentenceTransformers) |
| `LlmGateway` | `parse_intent(query)` | `parse_intent_with_llm()` (Groq) |

Remplacer Qdrant par Weaviate = écrire une nouvelle classe `WeaviateRepository`
qui implémente `VectorRepositoryGateway`. Zéro changement dans le use case ou
les entities.

### Règle de dépendance

```
entities/  ←  usecases/  ←  adapters/
```

Les flèches ne s'inversent jamais. `entities/` ne connaît pas `usecases/`.
`usecases/` ne connaît pas `adapters/`. `adapters/` implémente les ports de
`usecases/` et dépend des types définis dans `entities/`.

### Ce que cette séparation apporte

| Bénéfice | Concrètement |
|---|---|
| Testabilité | `entities/` se teste sans mock. Le use case se teste avec des mocks des ports. |
| Interchangeabilité | Passer de Groq à Claude = nouveau fichier dans `gateways/llm/`, zéro refactor |
| Lisibilité | Le use case dit *quoi*, les adapters disent *comment* |
| Pas de couplage DB dans le domaine | `entities/nlp/` ignore l'existence de PostgreSQL |

---

## Stratégie d'architecture de recherche — Pourquoi SQL en premier ?

Cette section documente les trois approches architecturalement distinctes pour
combiner recherche structurée et vectorielle, et justifie le choix fait pour ce
projet. Elle est écrite à un niveau stratégique, indépendamment de toute version
spécifique.

---

### Les trois options

#### Option A — SQL → Vectoriel *(architecture actuelle)*

```
Requête utilisateur
    │
    ▼  NLP Parser + QueryResolver
Clause WHERE PostgreSQL
    │  ensemble de candidats (contraintes dures respectées)
    ▼
Rerank sémantique
    │  similarité cosinus sur semantic_terms
    ▼
Résultats finaux (classés par sens, dans les contraintes)
```

**Exemple :** `"Maison Paris 500k lumineuse terrasse"`

Le pré-filtre SQL applique d'abord les contraintes dures :

```sql
WHERE city = 'Paris'
  AND property_type = 'house'
  AND mandate_price <= 500000
```

Puis le scoring sémantique classe les candidats survivants par `["lumineuse", "terrasse"]`.

| | |
|---|---|
| **Avantages** | PostgreSQL reste la source de vérité unique. Les contraintes métier dures sont appliquées avant tout calcul vectoriel. L'architecture s'aligne proprement sur les couches DDD / Clean Architecture. Pas de duplication du modèle de domaine dans les payloads Qdrant. Facile à expliquer, facile à auditer. Chaque couche est testable indépendamment. |
| **Inconvénients** | Le rerank est local (boucle Python sur les candidats, pas HNSW Qdrant natif). Les embeddings des candidats sont calculés au moment de la requête dans les premières versions. La scalabilité est plus faible que le filtrage natif par payload à grande échelle. |

---

#### Option B — Vectoriel → SQL

```
Requête utilisateur
    │
    ▼  embed la requête complète
Recherche Qdrant — top N global
    │  top-K candidats (pas encore d'application des contraintes)
    ▼
Filtrage SQL sur les candidats
    │
    ▼
Résultats finaux
```

| | |
|---|---|
| **Avantages** | Excellent pour les requêtes ambiguës ou entièrement qualitatives. L'index HNSW de Qdrant est utilisé à pleine capacité. Pas de duplication de payload nécessaire — Qdrant ne stocke que des IDs. |
| **Inconvénients** | **Si un bien pertinent n'est pas dans le top-K initial, il est perdu.** Les filtres SQL arrivent trop tard pour le récupérer. La précision sur les contraintes dures dépend entièrement du réglage du top-K. Les biens sémantiquement distants mais correspondant aux contraintes sont exclus silencieusement. Plus complexe à régler et à déboguer. |

Le paramètre `top_k` devient un curseur critique et fragile : trop petit perd
en précision, trop grand annule l'intérêt de la pré-sélection vectorielle.

---

#### Option C — Vectoriel + Filtres payload *(Qdrant comme moteur principal)*

```
Requête utilisateur
    │
    ▼  embed la requête + extraire les filtres structurés
Qdrant : recherche vectorielle AVEC filtre payload
    │  { "city": "Paris", "price": { "lte": 500000 } }
    ▼
Résultats finaux (pas de SQL pour le filtrage)
```

| | |
|---|---|
| **Avantages** | Débit maximal — moteur unique, aller-retour réseau unique. Le filtrage payload de Qdrant fonctionne au niveau de l'index HNSW (pas en post-filtre). Scalable horizontalement sans que PostgreSQL devienne un goulot d'étranglement. |
| **Inconvénients** | L'ensemble du modèle de domaine doit être dupliqué dans les payloads Qdrant. La synchronisation PostgreSQL ↔ Qdrant devient une charge de maintenance. Qdrant devient une quasi-base de données métier secondaire. Les règles métier complexes (jointures, agrégations, audit) nécessitent toujours PostgreSQL. Fort couplage entre le store vectoriel et le modèle de domaine. |

Pour un domaine immobilier riche avec mandats, agents, annonces et historiques
de ventes, l'Option C remplace un problème (scalabilité) par un problème plus
difficile (cohérence des données).

---

### Tableau comparatif

| Stratégie | Précision des contraintes | Puissance sémantique | Complexité | Maintenance | Scalabilité |
|---|---|---|---|---|---|
| **A — SQL → Vectoriel** | Haute (SQL applique les règles dures) | Bonne (rerank parmi les candidats) | Faible | Faible (source de vérité unique) | Moyenne |
| **B — Vectoriel → SQL** | Moyenne (dépend du top-K) | Haute (recherche vectorielle globale) | Moyenne | Moyenne (réglage du top-K) | Haute |
| **C — Qdrant principal** | Haute (filtres payload) | Haute (HNSW natif) | Haute | Haute (synchronisation dual-model) | Très haute |

---

### Pourquoi ce projet choisit SQL en premier

> **PostgreSQL gère la vérité. Qdrant gère le sens.**

Ce projet privilégie l'Option A pour les raisons suivantes :

1. **Lisibilité portfolio** — l'architecture est lisible et explicable à chaque
   couche. Un recruteur ou un CTO peut suivre le flux de données de la requête
   HTTP au résultat classé sans comprendre les internals HNSW.

2. **Intégrité des règles métier** — un utilisateur demandant des biens sous
   500k ne doit jamais voir des biens à 600k parce qu'un seuil top-K était trop
   agressif. Les contraintes dures sont binaires : SQL les applique sans ambiguïté.

3. **Source de vérité unique** — PostgreSQL possède toutes les données métier.
   Qdrant est un index dérivé, pas un store faisant autorité. Les vecteurs Qdrant
   périmés sont ignorés gracieusement ; ils ne corrompent jamais la sémantique des
   résultats.

4. **Testabilité** — la logique de pré-filtrage SQL est testable unitairement
   sans Qdrant. Le rerank sémantique est testable séparément avec des embeddings
   mockés. Chaque étape a une responsabilité claire et une frontière de test claire.

5. **Complexité progressive** — l'Option A scale à des dizaines de milliers de
   biens avec une latence acceptable. Le passage à l'Option C (filtrage payload
   Qdrant sur des champs à haute cardinalité) est une optimisation additive, pas
   une réécriture architecturale.

C'est le même raisonnement qui conduit les projets Symfony / Doctrine à garder
la base de données comme store faisant autorité et Elasticsearch comme index de
recherche dérivé — plutôt que de faire d'Elasticsearch le datastore principal
et de synchroniser en retour vers SQL.

---

### Roadmap d'évolution de la stratégie de recherche

#### V3 — actuelle
Pré-filtre SQL + scoring sémantique local (rerank Python sur les candidats SQL).

#### V3.1 — prochaine optimisation
Introduire le **filtrage payload Qdrant sur des champs sélectionnés** (`city`,
`price_max`, `property_type`). Qdrant applique les contraintes nativement au
niveau HNSW ; PostgreSQL n'est utilisé que pour l'hydratation et les champs non
indexés. Pas de duplication complète du modèle — seuls les trois champs de
filtrage à plus haute cardinalité sont dupliqués comme payloads.

#### V5 — Query Resolver Adaptatif
Le `QueryResolver` devient sensible à la stratégie :

| Profil d'intent | Stratégie choisie |
|---|---|
| Structuré dominant (city + price + rooms) | SQL d'abord → rerank sémantique optionnel |
| Sémantique dominant (qualitatif uniquement) | Vectoriel d'abord → validation SQL optionnelle |
| Mixte | Hybride dynamique — pré-filtre SQL + filtre payload Qdrant + rerank |

Cela ne nécessite aucun changement dans le parser NLP ou la couche HTTP — seulement la
fonction `resolve_query()` et une nouvelle branche dans `SearchProperty.execute()`.

---

##️ Choix techniques majeurs

### Pourquoi FastAPI ?

FastAPI génère automatiquement la doc OpenAPI, valide les schémas requête/réponse
via Pydantic, et est nativement async — une exigence quand chaque requête touche
à la fois PostgreSQL et Qdrant. L'alternative (Flask + sync) nécessiterait des
contournements avec des threads pour éviter de bloquer sur les appels DB.

Le système `Depends()` de FastAPI reflète le conteneur de services Symfony pour
l'injection de dépendances : la session de base de données est injectée dans les
handlers de route sans que le handler sache comment les sessions sont créées.

### Pourquoi SQLAlchemy Async ?

L'extension async de SQLAlchemy (`AsyncSession`, driver `asyncpg`) permet des
requêtes PostgreSQL non bloquantes. Avec un driver sync, chaque appel DB
bloquerait l'event loop pendant un appel Qdrant — éliminant tout bénéfice de
concurrence. SQLAlchemy fournit aussi une validation de requêtes à la compilation :
les requêtes sont compilées contre le dialecte PostgreSQL dans les tests,
détectant les erreurs de noms de colonnes sans base de données active.

### Pourquoi Pydantic ?

Deux rôles dans ce projet :

1. **Contrats I/O** (`adapters/controllers/schemas/`) : `PropertySearchResponse`
   valide et sérialise les réponses API. Toute inadéquation de type lève une
   `ValidationError` avant d'atteindre le client.

2. **DTO de domaine** (`PropertyIntent`) : l'interface stable entre la couche NLP
   et le Query Engine. Pydantic garantit que si le parser produit un intent mal
   formé, il échoue bruyamment à la frontière — pas silencieusement à l'intérieur
   d'un constructeur de requête SQL.

### Pourquoi Qdrant ?

| Critère | Qdrant | Elasticsearch |
|---|---|---|
| Similarité vectorielle native | Oui (index HNSW, cosinus/dot/euclidien) | Via plugin (kNN) |
| Empreinte Docker | ~200 MB image | ~1 Go+ |
| API REST + gRPC | Oui | REST uniquement |
| Filtrage avec vecteurs | Oui (filtres payload dans la recherche vectorielle) | Complexe |
| Client Python | Sync + Async | Sync uniquement (officiel) |

Qdrant a été conçu pour la recherche vectorielle dès le départ. Elasticsearch
l'a ajouté après coup. Pour un projet où la similarité vectorielle est le type
de requête principal, l'API de Qdrant est plus simple et ses caractéristiques
de performance plus prévisibles.

### Pourquoi sentence-transformers ?

`all-MiniLM-L6-v2` produit des embeddings de phrases en 384 dimensions optimisés
pour la similarité sémantique (entraîné avec apprentissage contrastif sur des
paires de phrases). Il est :

- **Rapide** : ~2000 phrases/seconde sur CPU
- **Compact** : modèle de 90 Mo, 384 floats par embedding contre 1536 pour `text-embedding-ada-002`
- **Local** : pas de clé API, pas de latence réseau, pas de coût par token
- **Suffisant** : pour les descriptions immobilières françaises, 384 dimensions capturent
  les distinctions sémantiques pertinentes entre "lumineux", "calme", "vue mer", etc.

### Pourquoi torch CPU uniquement ?

Le `pip install torch` par défaut télécharge le build GPU (~2 Go). Le backend
tourne dans Docker sur un ordinateur de développeur sans GPU. Le Dockerfile
installe torch CPU-only explicitement avant `requirements.txt` :

```dockerfile
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
```

| Build | Taille torch | Delta image |
|---|---|---|
| GPU (défaut) | ~2 Go | +2.2 Go |
| CPU uniquement | ~750 Mo | +850 Mo |

`sentence-transformers` dans `requirements.txt` ne déclare pas `torch` comme
dépendance — il est déjà présent. La version CPU-only est utilisée de façon
transparente.

### Pourquoi Docker dès le début ?

Chaque développeur, sur chaque machine, fait tourner la même version de
PostgreSQL, la même version de Qdrant, et la même version de Python. Il n'y a
pas de problèmes "ça marche sur ma machine" avec les extensions C de `asyncpg`
ou les versions du client Qdrant.

L'environnement complet se lance avec une seule commande :

```bash
docker compose up --build
```

Qdrant et PostgreSQL sont tous les deux persistants via des volumes Docker nommés.
Les volumes survivent à `docker compose down` et ne sont détruits qu'avec
`docker compose down -v`.

### Pourquoi >380 tests ?

Chaque fonction publique et chaque extracteur privé a sa propre classe de test.
La justification :

1. **Prévention des régressions** : le parser NLP a été refactorisé 5 fois
   (V1 → V1.1 → V2.1 → V2.2 → V2.3). Chaque refactorisation était sûre parce
   que les tests précédents détectaient tout changement de comportement.

2. **Discipline de mock** : les services async (Qdrant, PostgreSQL) sont mockés
   à leur site d'import, pas à leur source. Les tests tournent en ~2 secondes —
   pas d'infrastructure nécessaire.

3. **Documentation** : `TestExtractCity::test_text_order_paris_first` documente
   *pourquoi* le correctif d'ordre de set a été fait. Le test est l'explication.

4. **Confiance pour V5/V6** : ajouter la recherche hybride ou un parser LLM
   complet nécessite de modifier `SearchProperty` et `intent_parser.py`. Les
   380+ tests existants détectent immédiatement tout effet de bord non intentionnel.

---

## Stratégie de test

```
tests/
├── nlp/
│   ├── test_intent_schema.py         ← validation DTO PropertyIntent
│   ├── test_intent_parser.py         ← 100+ tests — chaque extracteur + intégration
│   ├── test_intent_parser_v4.py      ← pipeline portillon LLM (mock Groq)
│   └── test_fuzzy_matching.py        ← Levenshtein Python pur
├── llm/
│   ├── test_confidence_gate.py       ← logique du portillon (should_use_llm)
│   ├── test_intent_merger.py         ← fusion rule intent + llm intent
│   └── test_llm_validator.py         ← anti-hallucination (champs stricts)
├── query_engine/
│   ├── test_query_resolver.py        ← logique de routage sql/semantic/hybrid
│   └── test_pagination.py            ← slice Python + calcul total_pages
├── services/
│   ├── test_geospatial_service.py    ← bounding box + Haversine + get_city_center
│   └── geography/
│       └── test_distance.py          ← formule Haversine pure
├── embeddings/
│   ├── test_embedding_service.py     ← modèle singleton, dimensions vectorielles
│   ├── test_property_text_builder.py ← build_semantic_text()
│   └── test_similarity.py            ← cosine_similarity()
├── api/
│   └── test_property_search.py       ← couche HTTP avec use case mocké
└── core/
    └── test_config.py                ← lecture config pydantic-settings
```

**Tests unitaires** — fonctions pures, sans I/O, sans mocks nécessaires :
`_normalize`, `_tokenize`, `_extract_city`, `_is_noise_token`,
`_extract_compound_semantic_terms`, `resolve_query`, `compute_bounding_box`,
`filter_by_distance`, `cosine_similarity`

**Tests avec mocks** — I/O async remplacé par `AsyncMock` :
`QdrantRepository.search` (client Qdrant), `SearchProperty.execute` (dans les
tests API), `embed_text` (monkeypatché au niveau module), `parse_intent_with_llm`
(Groq, monkeypatché dans `test_intent_parser_v4.py`)

**Tests d'intégration** — pipeline complet via `parse_intent()` :
`"Maison Paris 500k"` → `semantic_terms=[]` → `sql_only`
`"studio vue mer lumineux"` → `semantic_terms=["vue mer", "lumineux"]` → `semantic_only`

**Pas de base de données active nécessaire** : les requêtes SQL sont compilées
contre le dialecte PostgreSQL avec `str(stmt.compile(dialect=postgresql.dialect()))`
— les noms de colonnes et les clauses `WHERE` sont vérifiés sans Postgres en cours
d'exécution.

**Exécution** : tous les tests tournent à l'intérieur du container Docker
(Python 3.12). Ne pas utiliser l'interpréteur hôte (Python 3.9, incompatible
avec la syntaxe `str | None`).

```bash
docker compose exec backend python -m pytest tests/ -v
```

---

## Commandes essentielles

### Démarrage

```bash
# Clone + configuration
cp backend/.env.example .env
# Éditer .env — définir SECRET_KEY avec : openssl rand -hex 32

# Premier build (~5 min — télécharge torch CPU + sentence-transformers)
docker compose up --build

# Démarrages suivants (instantané)
docker compose up -d
```

### Initialisation des données

```bash
# 1. Seed PostgreSQL — 81 biens, 10 agents, 81 descriptions (25 villes + communes proches)
docker compose exec backend python scripts/seed_database.py

# 2. Indexation Qdrant — génère les embeddings et les upsert
#    Premier run : télécharge all-MiniLM-L6-v2 (~90 Mo)
docker compose exec backend python scripts/index_properties_to_qdrant.py
```

Les deux scripts sont **idempotents** : `index_properties_to_qdrant.py` peut
être rejoué sans créer de doublons. `seed_database.py` est idempotent sur une
DB vide ; relancer sur une DB peuplée lève une erreur de contrainte unique.

**Séquence complète depuis zéro :**

```bash
docker compose up -d
docker compose exec backend python scripts/seed_database.py
docker compose exec backend python scripts/index_properties_to_qdrant.py
```

### Tests

```bash
# Suite complète
docker compose exec backend python -m pytest tests/ -v

# Module spécifique
docker compose exec backend python -m pytest tests/nlp/test_intent_parser.py -v

# Test unique
docker compose exec backend python -m pytest tests/nlp/test_intent_parser.py::TestExtractCity::test_text_order_paris_first -v

# Rapport rapide
docker compose exec backend python -m pytest tests/ --tb=short -q
```

### API — exemples de requêtes

```bash
# SQL uniquement — filtres structurés
curl "http://localhost:8000/properties/search?q=Maison+Paris+sous+500k"

# Sémantique uniquement — qualificatifs sans filtres structurés
curl "http://localhost:8000/properties/search?q=appartement+lumineux+vue+mer"

# Vérifier le routage (champ query_resolution dans la réponse)
curl -s "http://localhost:8000/properties/search?q=studio+calme+renove" | python -m json.tool | grep strategy
```

### Migrations Alembic

```bash
# Générer une migration après ajout de modèle
docker compose exec backend alembic revision --autogenerate -m "add_column_x"
docker compose exec backend alembic upgrade head

# Rollback
docker compose exec backend alembic downgrade -1
```

### Maintenance

```bash
# Logs backend
docker compose logs -f backend

# Reset complet (détruit volumes PG + Qdrant)
docker compose down -v
docker compose up -d
```

---

## Structure du projet

```
real-estate-ai-copilot/
│
├── docker-compose.yml
├── .env                          ← ignoré par git, copié depuis backend/.env.example
├── .gitignore
└── README.md
│
└── backend/
    ├── Dockerfile
    ├── requirements.txt          ← sentence-transformers, qdrant-client, fastapi…
    ├── .env.example
    ├── alembic.ini
    ├── alembic/
    │   ├── env.py                ← runner de migration compatible async
    │   └── versions/             ← fichiers de migration générés
    │
    ├── scripts/
    │   ├── seed_database.py      ← dataset demo (81 biens, 25 villes + communes proches)
    │   └── index_properties_to_qdrant.py  ← PG → embeddings → Qdrant
    │
    ├── tests/
    │   ├── nlp/                  ← parser intent, fuzzy matching, schéma
    │   ├── llm/                  ← portillon, merger, validator
    │   ├── query_engine/         ← resolver + pagination
    │   ├── services/             ← géospatial (bounding box, Haversine, get_city_center)
    │   ├── embeddings/           ← embedding adapter, text builder, similarity
    │   ├── api/                  ← couche HTTP
    │   └── core/                 ← config pydantic-settings
    │
    └── app/
        ├── main.py               ← point d'entrée FastAPI
        ├── core/
        │   ├── config.py         ← pydantic-settings, lit le .env
        │   ├── constants.py      ← SEMANTIC_SEARCH_QUERY_PREFIX et autres constantes
        │   └── settings/         ← config par domaine (embeddings, llm, search, vector_store)
        │
        ├── entities/             ← logique métier pure (stdlib + pydantic seulement)
        │   ├── property.py       ← DTO Property (lu depuis DB)
        │   ├── nlp/
        │   │   ├── intent_schema.py      ← PropertyIntent DTO — contrat stable NLP→Query
        │   │   ├── intent_parser.py      ← parser rule-based + orchestration V4
        │   │   ├── fuzzy_matching.py     ← Levenshtein Python pur
        │   │   ├── confidence_gate.py    ← logique de portillon LLM
        │   │   ├── intent_provider.py    ← provider hybride (rule + LLM)
        │   │   ├── llm_intent_schema.py  ← DTO LlmIntentResponse
        │   │   ├── llm_validator.py      ← anti-hallucination
        │   │   └── intent_merger.py      ← fusion rule intent + llm intent
        │   ├── geography/
        │   │   ├── distance.py           ← formule Haversine pure
        │   │   └── proximity.py          ← compute_bounding_box + filter_by_distance
        │   ├── search/
        │   │   ├── query_types.py        ← QueryStrategy, QueryResolution, SearchResult
        │   │   ├── query_resolver.py     ← resolve_query() — décision de routage pure
        │   │   └── pagination.py         ← paginate_results()
        │   └── embeddings/
        │       ├── text_builder.py       ← build_semantic_text()
        │       └── similarity.py         ← cosine_similarity()
        │
        ├── usecases/
        │   ├── gateway/          ← interfaces de ports (Protocol Python)
        │   │   ├── property_repository_gateway.py
        │   │   ├── embedding_gateway.py
        │   │   ├── vector_repository_gateway.py
        │   │   └── llm_gateway.py
        │   └── search_property/
        │       └── search_property_usecase.py  ← SearchProperty — use case principal
        │
        └── adapters/
            ├── controllers/      ← routers HTTP FastAPI
            │   ├── property_search.py
            │   └── schemas/
            │       └── property_search.py  ← contrats I/O Pydantic (requête/réponse)
            └── gateways/
                ├── db/
                │   ├── models/             ← ORM SQLAlchemy (Property, Agent, Mandate…)
                │   ├── repositories/
                │   │   ├── property_repository.py      ← requêtes SQL (filtres, proximité)
                │   │   └── geospatial_repository.py    ← get_city_center() SQL
                │   └── session.py
                ├── embedding/
                │   └── embedding_adapter.py  ← SentenceTransformers singleton
                ├── vector_db/
                │   ├── qdrant_repository.py  ← QdrantRepository.search() async
                │   └── qdrant_store.py       ← clients Qdrant sync/async + ensure_collection
                └── llm/
                    └── groq_adapter.py       ← parse_intent_with_llm() via Groq/OpenAI SDK
```

---

## 🗂️ Responsabilités des couches

| Package | Rôle | Ce qui N'y va PAS |
|---|---|---|
| `adapters/controllers/` | Routers HTTP, câblage DI FastAPI, sérialisation des réponses | Logique métier, requêtes DB |
| `adapters/controllers/schemas/` | Contrats I/O Pydantic (requête/réponse API) | Modèles ORM |
| `adapters/gateways/db/models/` | Définitions de classes ORM SQLAlchemy | Logique de requêtes |
| `adapters/gateways/db/repositories/` | Toutes les requêtes DB (un repository par agrégat) | HTTP, règles métier |
| `adapters/gateways/embedding/` | Singleton SentenceTransformers, `embed_text()` | Logique de domaine |
| `adapters/gateways/vector_db/` | Client Qdrant async, recherche vectorielle | SQL, HTTP |
| `adapters/gateways/llm/` | Appel Groq via SDK OpenAI, mode JSON | Validation, fusion d'intents |
| `usecases/gateway/` | Interfaces de ports (Protocol Python) — ce que le use case attend | Implémentations concrètes |
| `usecases/search_property/` | Orchestrateur principal — dispatch selon la stratégie | HTTP, SQL, Qdrant directs |
| `entities/nlp/` | Parsing de texte, extraction d'intent, reconnaissance d'entités, portillon LLM | HTTP, DB, Qdrant |
| `entities/search/` | Résolution de stratégie de routage, pagination | HTTP, NLP brut, I/O |
| `entities/geography/` | Formule Haversine, bounding box — math pure | SQL, HTTP |
| `entities/embeddings/` | Construction de texte sémantique, similarité cosinus | HTTP, logique métier |
| `core/` | Config globale (pydantic-settings), constantes partagées | Objets de domaine |

**Règle clé : `adapters/controllers/` vs `usecases/search_property/`**

`adapters/controllers/` est l'adaptateur HTTP — il traduit HTTP en Python et
Python en HTTP. Zéro logique ici.

`usecases/search_property/` est le cerveau de routage — étant donné un intent
parsé, il décide d'interroger PostgreSQL, Qdrant, ou les deux. C'est
l'intelligence centrale du système. Elle appartient à la couche use case, pas
enfouie dans du boilerplate HTTP.

---

## Endpoints

| Endpoint | URL |
|---|---|
| Recherche de biens | `GET /properties/search?q=` |
| Health check | `GET /health` |
| Swagger UI | http://localhost:8000/docs |
| Dashboard Qdrant | http://localhost:6333/dashboard |

**Structure de la réponse :**

```json
{
  "query": "appartement lumineux vue mer",
  "parsed_intent": {
    "intent": "property_search",
    "property_type": "apartment",
    "semantic_terms": ["lumineux", "vue mer"]
  },
  "query_resolution": {
    "strategy": "semantic_only",
    "reason": "qualitative terms only, no structured filters"
  },
  "count": 5,
  "results": [...]
}
```

Le champ `query_resolution` expose la décision de routage du moteur dans chaque
réponse — utile pour le débogage, les indicateurs UI et les tests de régression.

---

## Exemples de requêtes en langage naturel

Cette section documente les capacités du moteur NLP sur quatre niveaux progressifs
— des requêtes SQL déterministes aux requêtes de raisonnement sémantique IA futur.
Chaque exemple montre la requête utilisateur, l'intent structuré auquel elle est
mappée, et son statut de support actuel.

> Chaque requête est routée vers l'un des trois chemins d'exécution :
> `sql_only` (filtres structurés → PostgreSQL),
> `semantic_only` (termes qualitatifs → recherche vectorielle Qdrant), ou
> `hybrid` (pré-filtre SQL + rerank sémantique, V5).

### Légende des statuts

| Symbole | Signification |
|---|---|
| ✅ **Supporté** | Implémenté et couvert par la suite de tests |
| ⚡ **LLM à portillon** | Le parser rule-based gère les cas courants ; fallback Groq V4 pour les cas limites |
| 🔶 **Partiel** | Intent extrait correctement ; chemin d'exécution pas encore complet |
| 🚧 **Planifié** | Prévu dans la roadmap (V5 / V6) |

---

### V1 — Recherche de base

Requêtes déterministes : type de bien, ville, prix, nombre de pièces.
Elles mappent directement vers des clauses SQL `WHERE` — pas de calcul vectoriel, pas de LLM, pas d'ambiguïté.

---

**`"Maison à Paris"`** — ✅ Supporté

```json
{ "property_type": "house", "city": "Paris", "strategy": "sql_only" }
```

---

**`"Appartement à Lyon"`** — ✅ Supporté

```json
{ "property_type": "apartment", "city": "Lyon", "strategy": "sql_only" }
```

---

**`"Maison sous 500k"`** — ✅ Supporté

Le suffixe `k` est pré-traité comme un token parasite : `500k → 500000`.
Le caractère `"k"` est filtré avant l'extraction sémantique, donc il n'atteint jamais la recherche vectorielle.

```json
{ "property_type": "house", "max_price": 500000, "strategy": "sql_only" }
```

---

**`"Appartement 3 chambres à Marseille"`** — ✅ Supporté

Les formats de pièces `T3`, `F4`, `3 pièces`, `3 chambres` se résolvent tous vers `min_rooms`.

```json
{ "property_type": "apartment", "city": "Marseille", "min_rooms": 3, "strategy": "sql_only" }
```

---

**`"Maison avec jardin"`** — 🔶 Partiel

`jardin` est un qualificatif sémantique du domaine (explicitement préservé des stopwords).
Combiné avec un filtre structuré (`property_type`), cela devient une requête hybride.
L'extraction d'intent est correcte ; l'exécution hybride nécessite V5.

```json
{ "property_type": "house", "semantic_terms": ["jardin"], "strategy": "hybrid" }
```

---

### V2 — Filtres avancés

Requêtes business-aware : type de mandat, ancienneté de publication, filtres composés.
Tous les champs routent vers SQL — pas de calcul vectoriel requis.

---

**`"Biens à Paris avec mandat exclusif"`** — ✅ Supporté

```json
{ "city": "Paris", "mandate_type": "exclusive", "strategy": "sql_only" }
```

---

**`"Appartements exclusifs à Lyon"`** — ✅ Supporté

```json
{ "property_type": "apartment", "city": "Lyon", "mandate_type": "exclusive", "strategy": "sql_only" }
```

---

**`"Biens publiés depuis plus de 30 jours"`** — ✅ Supporté

Pattern de phrase `depuis plus de X jours` → `published_more_than_days_ago: 30`.

```json
{ "published_more_than_days_ago": 30, "strategy": "sql_only" }
```

---

**`"Biens publiés il y a plus de 60 jours"`** — ✅ Supporté

Formulation alternative — même extraction, même champ. Plusieurs formulations sont normalisées vers un seul filtre canonique.

```json
{ "published_more_than_days_ago": 60, "strategy": "sql_only" }
```

---

**`"Biens publiés depuis moins de 7 jours"`** — ✅ Supporté

Pattern de phrase `depuis moins de X jours` → `published_less_than_days_ago: 7`.

```json
{ "published_less_than_days_ago": 7, "strategy": "sql_only" }
```

---

**`"Biens exclusifs publiés depuis 45 jours"`** — ✅ Supporté

Filtre composé : type de mandat + ancienneté de publication, résolu en un seul passage de parsing.

```json
{ "mandate_type": "exclusive", "published_more_than_days_ago": 45, "strategy": "sql_only" }
```

---

### V3 — Recherche par agent / conseiller

Requêtes ciblant le portefeuille d'un agent spécifique.
Les filtres agent se composent librement avec tous les filtres V1 et V2.

---

**`"Les biens de Marie Dupont"`** — ✅ Supporté

Prénom + nom de famille extraits. Les verbes possessifs (`de`, `d'`) et les articles sont des stopwords ; le nom est préservé.

```json
{ "agent_name": "Marie Dupont", "strategy": "sql_only" }
```

---

**`"Voir les biens de Jean Martin"`** — ✅ Supporté

Les verbes de recherche (`voir`, `montrer`, `afficher`) sont des stopwords ; le nom de l'agent n'est pas affecté.

```json
{ "agent_name": "Jean Martin", "strategy": "sql_only" }
```

---

**`"Biens exclusifs de Sophie Bernard"`** — ✅ Supporté

Filtre agent + type de mandat combinés en une seule requête SQL.

```json
{ "agent_name": "Sophie Bernard", "mandate_type": "exclusive", "strategy": "sql_only" }
```

---

**`"Biens de Marie Dupont publiés depuis plus de 30 jours"`** — ✅ Supporté

Filtre structuré à trois dimensions : agent + ancienneté de publication. Démontre que les filtres V2 et V3 se composent sans conflit.

```json
{ "agent_name": "Marie Dupont", "published_more_than_days_ago": 30, "strategy": "sql_only" }
```

---

### Recherche de proximité — Ville proche

Requêtes qui cherchent autour d'une ville plutôt qu'à l'intérieur.
Le moteur détecte un pattern de proximité, calcule le centre de la ville depuis
les coordonnées de biens existants, applique un pré-filtre SQL par bounding box,
puis affine avec la distance Haversine en Python.

---

**`"Maison proche de Paris"`** — ✅ Supporté

```json
{ "property_type": "house", "nearby_city": "Paris", "search_radius_km": 15, "strategy": "sql_only" }
```

Retourne les maisons à Vincennes, Neuilly-sur-Seine, Levallois-Perret, Montreuil… (dans un rayon de 15 km).

---

**`"Appartement à côté de Lyon"`** — ✅ Supporté

```json
{ "property_type": "apartment", "nearby_city": "Lyon", "search_radius_km": 15, "strategy": "sql_only" }
```

Retourne les appartements à Villeurbanne, Caluire-et-Cuire… La réponse inclut `expanded_cities` listant chaque commune trouvée dans le rayon.

---

**`"Biens autour de Marseille"`** — ✅ Supporté

```json
{ "nearby_city": "Marseille", "search_radius_km": 15, "strategy": "sql_only" }
```

Pas de type de bien spécifié — retourne tous les types dans un rayon de 15 km (Allauch, Plan-de-Cuques…).

---

**`"Biens aux alentours de Nantes"`** — ✅ Supporté

```json
{ "nearby_city": "Nantes", "search_radius_km": 15, "strategy": "sql_only" }
```

Le pattern `aux alentours de` est l'un des six préfixes de proximité supportés.

---

**`"Maison dans un rayon de 20km de Bordeaux"`** — ✅ Supporté

Le rayon explicite remplace le défaut de 15 km.

```json
{ "property_type": "house", "nearby_city": "Bordeaux", "search_radius_km": 20, "strategy": "sql_only" }
```

---

**`"Appartement T3 pres de Toulouse sous 300k"`** — ✅ Supporté

Proximité + type de bien + nombre de pièces + prix max, tous résolus en un seul passage.
`nearby_city` et `city` sont mutuellement exclusifs — jamais définis simultanément.

```json
{ "property_type": "apartment", "nearby_city": "Toulouse", "search_radius_km": 15, "min_rooms": 3, "max_price": 300000, "strategy": "sql_only" }
```

---

**`"Biens dans les environs de Le Havre"`** — ✅ Supporté

Le nom de ville multi-mots (`Le Havre`) est correctement extrait via la boucle stop-token.

```json
{ "nearby_city": "Le Havre", "search_radius_km": 15, "strategy": "sql_only" }
```

---

**`"Maison à Paris"`** vs **`"Maison proche de Paris"`** — ✅ Invariant garanti

| Requête | `city` | `nearby_city` | Périmètre |
|---|---|---|---|
| `"Maison à Paris"` | `Paris` | `null` | Paris uniquement |
| `"Maison proche de Paris"` | `null` | `Paris` | ≤ 15 km autour de Paris |

Les deux champs sont mutuellement exclusifs. Le parser définit l'un ou l'autre, jamais les deux.

---

**`"Biens proche de VilleInconnue"`** — ✅ Géré gracieusement

Si aucun bien n'existe dans la ville cible, le centre ne peut pas être calculé.
L'API retourne un ensemble de résultats vide (pas une erreur), avec `total_count: 0`.

---

### V4 — Hybride & Vision future

Requêtes qui combinent des contraintes dures avec une intention qualitative, ou
qui nécessitent un raisonnement sur des données que le modèle actuel ne capture
pas encore (historique de prix, similarité de biens, rendement d'investissement).

---

**`"Biens familiaux à Paris sous 500k"`** — 🚧 Planifié

`familial` est un qualificatif lifestyle. Les filtres structurés (`city`, `max_price`)
sont extraits aujourd'hui. L'exécution hybride — pré-filtre SQL + rerank sémantique
sur `familial` — nécessite V5.

```json
{ "city": "Paris", "max_price": 500000, "semantic_terms": ["familial"], "strategy": "hybrid" }
```

---

**`"Maisons lumineuses avec jardin"`** — 🔶 Partiel

Les termes sémantiques sont extraits correctement. La détection de qualificatifs
composés gère les termes multi-mots. L'exécution hybride (V5) est nécessaire pour
appliquer `property_type` tout en classant par score sémantique.

```json
{ "property_type": "house", "semantic_terms": ["lumineux", "jardin"], "strategy": "hybrid" }
```

---

**`"Appartements en baisse de prix depuis 30 jours"`** — 🚧 Planifié

Nécessite un modèle d'historique de prix — suivre les changements de `mandate_price`
dans le temps via la chronologie `mandate_sales`. Les signaux de tendance de prix
sont hors du schéma actuel.

```json
{ "property_type": "apartment", "price_trend": "decreasing", "price_trend_days": 30, "strategy": "hybrid" }
```

---

**`"Mandats exclusifs de Marie Dupont à Lyon"`** — ✅ Supporté → 🚧 Couche sémantique planifiée

L'extraction structurée est entièrement supportée aujourd'hui (agent + ville + type de mandat → SQL).
Futur : rerank sémantique du portefeuille de cet agent par critères qualitatifs.

```json
{ "agent_name": "Marie Dupont", "city": "Lyon", "mandate_type": "exclusive", "strategy": "sql_only" }
```

---

**`"Biens similaires à cet appartement"`** — 🚧 Planifié

Nécessite une similarité vectorielle basée sur une référence : embed la description
d'un bien spécifique et l'utiliser comme vecteur de requête, plutôt qu'une phrase
tapée par l'utilisateur. Nouveau type d'intent et paramètre API (`reference_id`) nécessaires.

```json
{ "intent": "similar_properties", "reference_property_id": "<uuid>", "strategy": "semantic_only" }
```

---

**`"Biens avec fort potentiel d'investissement"`** — 🚧 Planifié

Signal sémantique composite. `investissement` et `potentiel` survivent aujourd'hui
au filtrage des stopwords et atteignent Qdrant. La précision complète nécessite un
modèle de rendement/ratio prix hors des embeddings de descriptions actuels.

```json
{ "semantic_terms": ["investissement", "potentiel"], "strategy": "semantic_only" }
```

---

### Résumé des capacités

| Capacité | Statut | Notes |
|---|---|---|
| Filtre ville | ✅ Supporté | Résolu dans l'ordre du texte ; correspondance floue (Levenshtein ≤ 1) |
| Prix max | ✅ Supporté | Suffixe `k` pré-traité (`500k → 500000`) |
| Type de bien | ✅ Supporté | 10+ synonymes (`pavillon`, `duplex`, …) + tolérance aux fautes |
| Nombre de pièces | ✅ Supporté | `T3`, `F4`, `3 chambres`, `3 pièces` |
| Type de transaction | ✅ Supporté | Vente / location / `loc` |
| Type de mandat | ✅ Supporté | Exclusif / simple |
| Ancienneté de publication | ✅ Supporté | Les deux directions — `depuis plus de` et `depuis moins de` |
| Nom d'agent | ✅ Supporté | Prénom + nom de famille ; se compose avec tous les autres filtres |
| Recherche de proximité | ✅ Supporté | 6 préfixes (`proche de`, `à côté de`, …) + rayon explicite (`dans un rayon de Xkm`) |
| Noms de villes multi-mots | ✅ Supporté | `Le Havre`, `Boulogne-Billancourt` — extraction stop-token |
| Qualificatifs sémantiques | ✅ Supporté | Tokens simples + termes composés (`vue mer`, `centre ville`) |
| Tolérance aux fautes (dist ≤ 1) | ✅ Supporté | Levenshtein rule-based, sans coût LLM |
| Tolérance aux fautes (dist > 1) | ⚡ LLM à portillon | Fallback Groq V4 ; `llama-3.1-8b-instant`, `temperature=0` |
| Synonymes inconnus | ⚡ LLM à portillon | Le LLM comble les lacunes quand le parser rule-based extrait < 2 signaux |
| Hybride SQL + sémantique | 🚧 Planifié | V5 — pré-filtre SQL → rerank Qdrant |
| Recherche lifestyle | 🔶 Partiel | Termes sémantiques extraits ; exécution hybride nécessite V5 |
| Tendance / historique de prix | 🚧 Planifié | Nécessite un modèle d'historique de prix (V6) |
| Recherche de bien similaire | 🚧 Planifié | Ancre vectorielle basée sur une référence (V6) |
| Potentiel d'investissement | 🔶 Partiel | Termes sémantiques atteignent Qdrant ; modèle de rendement nécessaire pour la précision |
| Requêtes multi-villes | 🚧 Planifié | Une seule ville résolue aujourd'hui (ordre du texte, première correspondance) |

---

## Dataset

| Table | Lignes |
|---|---|
| `agents` | 10 |
| `properties` | 81 (réparties sur 25 villes) |
| `descriptions` | 81 (français, texte réaliste) |
| `property_listings` | 77 |
| `mandates` | 81 |
| `mandate_sales` | 62 |
| `mandate_rentals` | 19 |

**Villes principales :** Paris · Lyon · Bordeaux · Rennes · Le Havre · Boulogne-Billancourt ·
Saint-Denis · Toulouse · Marseille · Nantes

**Communes proches** (pour la recherche de proximité) :
Vincennes · Neuilly-sur-Seine · Levallois-Perret · Montreuil *(zone Paris)* ·
Villeurbanne · Caluire-et-Cuire *(zone Lyon)* ·
Allauch · Plan-de-Cuques *(zone Marseille)* ·
Mérignac · Pessac *(zone Bordeaux)* ·
Blagnac · Colomiers *(zone Toulouse)* ·
Saint-Herblain · Rezé *(zone Nantes)* ·
Cesson-Sévigné *(zone Rennes)*

---

## Variables d'environnement

Voir `backend/.env.example` pour la référence complète. Le `.env` racine est
ignoré par git — ne jamais le committer.

| Variable | Rôle |
|---|---|
| `DATABASE_URL` | URL SQLAlchemy async complète (driver `asyncpg`) |
| `QDRANT_HOST` | Hostname Qdrant (nom de service Docker : `qdrant`) |
| `QDRANT_PORT` | Port gRPC Qdrant (défaut : `6334`) |
| `QDRANT_COLLECTION_NAME` | Collection Qdrant utilisée pour les embeddings de biens |
| `APP_ENV` | `development` / `staging` / `production` |
| `APP_DEBUG` | Active les logs de requêtes SQLAlchemy + debug FastAPI |
| `SECRET_KEY` | Générer avec `openssl rand -hex 32` |
| `EMBEDDING_MODEL_NAME` | Modèle SentenceTransformers utilisé pour la recherche sémantique |
| `GROQ_API_KEY` | Active le parser LLM à portillon quand présente |
| `GROQ_BASE_URL` | Endpoint Groq compatible OpenAI |
| `GROQ_MODEL` | Modèle Groq utilisé pour l'extraction d'intent structurée |
| `GROQ_TIMEOUT_SECONDS` | Timeout pour l'appel API Groq |
| `GROQ_MAX_TOKENS` | Borne supérieure pour la longueur de réponse JSON du LLM |
| `GROQ_TEMPERATURE` | Maintenu à `0` pour une extraction déterministe |
| `GROQ_SEED` | Seed fixe pour des sorties LLM reproductibles |

### Choix de modèles

- **Modèle d'embedding** : `sentence-transformers/all-MiniLM-L6-v2`
  Choisi pour l'inférence CPU locale, la faible empreinte, et les embeddings
  en 384 dimensions suffisants pour la recherche sémantique immobilière.
- **Préfixe de requête sémantique** : `bien immobilier`
  Conservé comme constante métier dans le code, pas comme config d'environnement,
  car c'est une phrase de domaine stable utilisée pour ancrer les requêtes
  sémantiques dans le domaine immobilier.
- **Fournisseur LLM** : Groq via SDK compatible OpenAI
  Choisi pour garder l'API client simple tout en ajoutant un fallback hébergé
  à faible latence pour la correction de fautes et l'enrichissement sémantique.
- **Modèle LLM** : `llama-3.1-8b-instant`
  Choisi car rapide, économique/free-tier friendly, et suffisant pour l'extraction
  JSON structurée avec `temperature=0` et un validator.

---

## Stratégie de pagination par type de requête

La pagination V1 expose `page`, `per_page` et `total_pages` dans chaque réponse
de recherche. L'implémentation diffère selon la stratégie car chaque stratégie
récupère les résultats différemment.

### API

```
GET /properties/search?q=maison Paris&page=2&per_page=5
```

```json
{
  "query": "maison Paris",
  "count": 5,
  "page": 2,
  "per_page": 5,
  "total_pages": 11,
  "results": [...]
}
```

Défauts : `page=1`, `per_page=10`. Validation : `page >= 1`, `1 <= per_page <= 100`.

### Stratégie SQL — pagination native en base

```
Intent SQL_ONLY (filtres structurés uniquement) :
  Requête COUNT(*)  →  total_count  (exact, utilise les mêmes clauses WHERE)
  SELECT ... LIMIT per_page OFFSET (page-1)*per_page
```

Équivalent SQLAlchemy de `setFirstResult(offset)->setMaxResults(perPage)` en Doctrine.
Le total est **exact**. Le moteur DB ne charge que les N lignes de la page demandée — O(log n) avec des index.

### Stratégie sémantique — slice Python après Qdrant

```
Intent SEMANTIC_ONLY (termes en texte libre uniquement) :
  top_k = page * per_page   →  Qdrant retourne assez pour couvrir la page
  hydratation depuis PostgreSQL   →  objets Property
  paginate_results(all, page, per_page)  →  slice Python
```

Équivalent PHP : `array_slice($results, $offset, $perPage)`.
`total_count` est **approximatif** en V1 (= résultats retournés par Qdrant, pas la taille réelle du corpus).
Upgrade V2 : utiliser l'endpoint `count` de Qdrant.

### Stratégie hybride — slice Python après scoring en mémoire

```
Intent HYBRID (filtres structurés + termes sémantiques) :
  Pré-filtre SQL  →  biens candidats
  cosine_similarity par candidat  →  liste scorée (triée par score DESC)
  paginate_results(all, page, per_page)  →  slice Python
```

`total_count` est **exact** (tous les résultats sont en mémoire avant le découpage).

### Résumé des compromis

| Stratégie | total_count | Performance à l'échelle | Implémentation |
|---|---|---|---|
| `sql_only` | Exact (COUNT*) | O(log n) — scalable | OFFSET/LIMIT natif |
| `semantic_only` | Approximatif | Acceptable V1 | Slice Python |
| `hybrid` | Exact | Acceptable V1 (cap top_k=20) | Slice Python |

---

## Frontend

### Stack

| Outil | Rôle |
|---|---|
| React 18 | Bibliothèque UI |
| Vite | Build tool + serveur de dev |
| TypeScript | Typage statique |
| Tailwind CSS v3 | Styles |
| TanStack Query v5 | État serveur, cache, états de chargement |

### Lancement

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### Variable d'environnement

```bash
# frontend/.env
VITE_API_BASE_URL=http://localhost:8000
```

Le backend doit être disponible à cette URL (voir `docker compose up`).

### Fonctionnalités

- Saisie en langage naturel avec appel à `GET /properties/search`
- Affichage des résultats avec type, ville, prix, score de pertinence
- Badges : "Pertinent" (score ≥ 70%), "Proche" (recherche de proximité), "Correspond bien" (hybrid)
- Pagination page par page
- Debug panel sticky : intent NLP complet, stratégie, termes sémantiques, villes étendues

---

## Environnement de production

| Composant | Hébergeur | URL |
|---|---|---|
| Frontend | Vercel | https://real-estate-semantic-search.vercel.app |
| Backend (FastAPI) | Render (Docker) | https://real-estate-semantic-search.onrender.com |
| PostgreSQL | Aiven (managed, SSL) | `real-estate-semantic-search-db.*.aivencloud.com:23092` |
| Vector DB | Qdrant Cloud (AWS eu-west-1) | `*.eu-west-1-0.aws.cloud.qdrant.io` |

### Choix d'hébergement

- **Vercel** — déploiement automatique depuis GitHub, optimisé pour les sites statiques Vite/React. Build command : `vite build`, Root directory : `frontend/`.
- **Render** — service Docker, détecte `./backend/Dockerfile`. Le port est dynamique (`$PORT`). Plan Starter (free tier avec cold start).
- **Aiven** — PostgreSQL managé avec SSL obligatoire. Connection string au format `postgresql+asyncpg://...?ssl=require` pour asyncpg.
- **Qdrant Cloud** — cluster vectoriel managé. Connexion via URL HTTPS + API key (variables `QDRANT_URL` + `QDRANT_API_KEY`).

### Variables d'environnement production (Render)

```
APP_ENV=production
APP_DEBUG=false
DATABASE_URL=postgresql+asyncpg://<user>:<pass>@<host>:<port>/defaultdb?ssl=require
QDRANT_URL=https://<cluster>.qdrant.io
QDRANT_API_KEY=<key>
QDRANT_COLLECTION_NAME=properties
GROQ_API_KEY=<key>
GROQ_MODEL=llama-3.1-8b-instant
USE_LLM=true
SECRET_KEY=<generated>
ALLOWED_ORIGINS=https://real-estate-semantic-search.vercel.app
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
```

> **Note Render** : les variables d'environnement doivent être saisies manuellement dans le dashboard (New → Web Service). Le fichier `render.yaml` n'est lu automatiquement que via New → Blueprint.

---

## Stack technique

| Service | Image / Runtime | Port(s) |
|---|---|---|
| Frontend | React + Vite | 5173 |
| Backend | Python 3.12 + FastAPI | 8000 |
| PostgreSQL | postgres:16-alpine | 5432 |
| Qdrant | qdrant/qdrant:v1.9.2 | 6333 / 6334 |
