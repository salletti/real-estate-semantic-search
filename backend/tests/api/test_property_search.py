"""
Tests — GET /properties/search
================================

STRATÉGIE DE TEST
------------------
On teste ici la responsabilité du ROUTER uniquement :
  - Le routing HTTP (bonne URL, bon verbe)
  - La validation des paramètres (q obligatoire, min_length=1, page/per_page contraintes)
  - La sérialisation ORM → JSON (PropertySearchResult, alias type→property_type)
  - La structure de la réponse (query, parsed_intent, query_resolution, count, page, per_page, total_pages, results)

On NE reteste PAS :
  - parse_intent()      → couvert dans tests/nlp/
  - resolve_query()     → couvert dans tests/query_engine/
  - paginate_results()  → couvert dans tests/query_engine/test_pagination.py

Pour isoler le router, on utilise deux techniques :
  1. app.dependency_overrides[get_db] → injecte une fausse session (pas de PostgreSQL)
  2. mocker.patch("app.adapters.controllers.property_search.SearchProperty.execute") → contrôle ce que le usecase retourne

Règle d'or du mock Python :
    On mocke le nom tel qu'il est importé dans le module testé.

    # ✓ Correct — on patche la méthode dans le module qui l'utilise
    mocker.patch("app.adapters.controllers.property_search.SearchProperty.execute", ...)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.adapters.gateways.db.session import get_db
from app.main import app
from app.entities.nlp.intent_provider import parse_user_intent
from app.entities.nlp.intent_schema import PropertyIntent
from app.entities.search.query_types import QueryResolution, QueryStrategy, SearchResult


# =============================================================================
# Helpers
# =============================================================================

def make_fake_property(**overrides) -> MagicMock:
    """Fabrique un faux objet Property ORM avec des valeurs réalistes.

    On utilise MagicMock car PropertySearchResult.model_validate() lit les attributs
    via from_attributes=True — un MagicMock avec setattr() suffit.

    Note : l'attribut clé est "type" (nom de la colonne ORM),
    mappé vers "property_type" dans le JSON de sortie via Field(validation_alias="type").
    """
    prop = MagicMock()
    prop.id = 1
    prop.city = "Paris"
    prop.type = "house"                  # ← ORM : Property.type
    prop.transaction_type = "sale"
    prop.mandate_price = 450_000.0
    prop.rooms_count = 4
    prop.created_at = datetime(2024, 3, 10, 14, 0, 0, tzinfo=timezone.utc)
    prop.description_fr = None           # MagicMock auto-génère sinon un non-string

    for key, value in overrides.items():
        setattr(prop, key, value)

    return prop


def make_fake_search_result(
    score: float | None = None,
    strategy: QueryStrategy = QueryStrategy.sql_only,
    **prop_overrides,
) -> SearchResult:
    """Wrape un faux Property dans un SearchResult."""
    return SearchResult(
        property=make_fake_property(**prop_overrides),
        score=score,
        strategy=strategy,
    )



def _make_usecase_result(
    search_results: list[SearchResult] | None = None,
    total: int | None = None,
    resolution: QueryResolution | None = None,
    intent: PropertyIntent | None = None,
) -> dict:
    """Fabrique un résultat de usecase pour mocker SearchPropertyUsecase.execute().

    Le format reflète ce que SearchPropertyUsecase.execute() retourne réellement.
    """
    results = search_results if search_results is not None else [make_fake_search_result()]
    prop_results = [{"property": sr.property, "score": sr.score} for sr in results]
    total_count = total if total is not None else len(prop_results)
    if resolution is None:
        resolution = QueryResolution(
            strategy=QueryStrategy.sql_only,
            has_structured_filters=True,
            has_semantic_terms=False,
            reason="test",
        )
    return {
        "query": "test",
        "resolution": resolution,
        "intent": intent if intent is not None else PropertyIntent(),
        "results": prop_results,
        "total": total_count,
        "page": 1,
        "page_size": 10,
        "total_pages": max(1, total_count),
    }


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_session() -> AsyncMock:
    """Fausse AsyncSession — aucune connexion PostgreSQL.

    execute() est configuré pour retourner un MagicMock (sync) dont
    scalars() est itérable — évite l'erreur "coroutine is not iterable"
    quand _fetch_descriptions() itère sur result.scalars().
    """
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value = []
    session.execute.return_value = mock_result
    return session


@pytest.fixture
async def client(mock_session: AsyncMock) -> AsyncClient:
    """AsyncClient branché sur l'app FastAPI avec la DB mockée.

    app.dependency_overrides remplace get_db pour toute la durée du test.
    Après le test, on nettoie pour ne pas polluer les autres tests.

    Symfony équivalent :
        $client = static::createClient();
        // + mock du service injecté dans le container de test
    """
    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# =============================================================================
# Cas nominal — requête complète
# =============================================================================

class TestPropertySearchSuccess:
    async def test_returns_200(self, client: AsyncClient, mocker):
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result()),
        )
        response = await client.get("/properties/search?q=Maison%20à%20Paris")
        assert response.status_code == 200

    async def test_response_contains_required_keys(self, client: AsyncClient, mocker):
        """La réponse doit contenir : query, parsed_intent, query_resolution, count,
        page, per_page, total_pages, results."""
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result()),
        )
        data = (await client.get("/properties/search?q=Maison%20à%20Paris")).json()

        assert "query" in data
        assert "parsed_intent" in data
        assert "query_resolution" in data
        assert "count" in data
        assert "page" in data
        assert "per_page" in data
        assert "total_pages" in data
        assert "results" in data

    async def test_query_is_echoed_in_response(self, client: AsyncClient, mocker):
        """Le champ query doit refléter exactement ce que l'utilisateur a tapé."""
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(search_results=[])),
        )
        data = (await client.get("/properties/search?q=Studio Bordeaux")).json()
        assert data["query"] == "Studio Bordeaux"

    async def test_count_matches_results_length(self, client: AsyncClient, mocker):
        """count doit être égal à len(results) — cohérence de la réponse."""
        fake_results = [make_fake_search_result(id=i) for i in range(3)]
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(search_results=fake_results)),
        )
        data = (await client.get("/properties/search?q=Appartement Lyon")).json()

        assert data["count"] == 3
        assert len(data["results"]) == 3

    async def test_default_page_is_1(self, client: AsyncClient, mocker):
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result()),
        )
        data = (await client.get("/properties/search?q=Paris")).json()
        assert data["page"] == 1

    async def test_default_per_page_is_10(self, client: AsyncClient, mocker):
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result()),
        )
        data = (await client.get("/properties/search?q=Paris")).json()
        assert data["per_page"] == 10

    async def test_custom_page_and_per_page_echoed_in_response(self, client: AsyncClient, mocker):
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(total=50)),
        )
        data = (await client.get("/properties/search?q=Paris&page=3&per_page=5")).json()
        assert data["page"] == 3
        assert data["per_page"] == 5

    async def test_total_pages_calculation(self, client: AsyncClient, mocker):
        """ceil(53 / 5) = 11 total_pages."""
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(search_results=[], total=53)),
        )
        data = (await client.get("/properties/search?q=Paris&per_page=5")).json()
        assert data["total_pages"] == 11

    async def test_total_pages_is_1_for_empty_results(self, client: AsyncClient, mocker):
        """Pas de résultats → total_pages = 1 (convention UI)."""
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(search_results=[], total=0)),
        )
        data = (await client.get("/properties/search?q=Paris")).json()
        assert data["total_pages"] == 1


# =============================================================================
# Sérialisation — shape du résultat individuel
# =============================================================================

class TestPropertyResultShape:
    @pytest.fixture(autouse=True)
    def patch_executor(self, mocker):
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result()),
        )

    async def test_result_has_all_required_fields(self, client: AsyncClient):
        data = (await client.get("/properties/search?q=Maison Paris")).json()
        result = data["results"][0]

        assert "id" in result
        assert "city" in result
        assert "property_type" in result
        assert "transaction_type" in result
        assert "mandate_price" in result
        assert "rooms_count" in result
        assert "created_at" in result
        assert "score" in result

    async def test_score_is_null_for_sql_only(self, client: AsyncClient):
        """score = null dans le JSON pour une stratégie sql_only (aucun score sémantique)."""
        data = (await client.get("/properties/search?q=Maison Paris")).json()
        assert data["results"][0]["score"] is None

    async def test_type_alias_maps_to_property_type(self, client: AsyncClient):
        """Vérifie le mapping critique : Property.type → "property_type" dans le JSON.

        C'est le cas d'usage de Field(validation_alias="type") dans PropertySearchResult :
          - ORM : prop.type = "house"
          - JSON : { "property_type": "house" }
          - Le mot "type" ne doit PAS apparaître comme clé dans le JSON de sortie.
        """
        data = (await client.get("/properties/search?q=Maison Paris")).json()
        result = data["results"][0]

        assert result["property_type"] == "house"
        assert "type" not in result          # "type" est l'alias interne, pas la clé JSON

    async def test_result_field_values(self, client: AsyncClient):
        data = (await client.get("/properties/search?q=Maison Paris")).json()
        result = data["results"][0]

        assert result["id"] == 1
        assert result["city"] == "Paris"
        assert result["transaction_type"] == "sale"
        assert result["mandate_price"] == 450_000.0
        assert result["rooms_count"] == 4

    async def test_score_is_float_when_semantic(self, client: AsyncClient, mocker):
        """score est un float dans le JSON quand la stratégie est semantic/hybrid."""
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(
                search_results=[make_fake_search_result(score=0.84, strategy=QueryStrategy.hybrid)]
            )),
        )
        data = (await client.get("/properties/search?q=Maison lumineuse Paris")).json()
        assert data["results"][0]["score"] == pytest.approx(0.84)


# =============================================================================
# parsed_intent — transparence du pipeline NLP
# =============================================================================

class TestParsedIntentInResponse:
    async def test_parsed_intent_is_a_dict(self, client: AsyncClient, mocker):
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(search_results=[])),
        )
        data = (await client.get("/properties/search?q=Maison Paris")).json()
        assert isinstance(data["parsed_intent"], dict)

    async def test_parsed_intent_has_intent_field(self, client: AsyncClient, mocker):
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(search_results=[])),
        )
        data = (await client.get("/properties/search?q=Maison Paris")).json()
        assert "intent" in data["parsed_intent"]

    async def test_maison_paris_intent_parsed_correctly(self, client: AsyncClient, mocker):
        """parse_intent() est appelée réellement (pas mockée) — on vérifie le pipeline end-to-end."""
        parsed = parse_user_intent("Maison a Paris")
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(search_results=[], intent=parsed)),
        )
        data = (await client.get("/properties/search?q=Maison a Paris")).json()
        intent = data["parsed_intent"]

        assert intent["city"] == "Paris"
        assert intent["property_type"] == "house"

    async def test_unknown_query_has_unknown_intent(self, client: AsyncClient, mocker):
        """Une phrase sans mots-clés reconnus → intent = 'unknown', pas d'erreur."""
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(search_results=[], total=0)),
        )
        data = (await client.get("/properties/search?q=bonjour")).json()

        assert data["parsed_intent"]["intent"] == "unknown"
        assert data["count"] == 0


# =============================================================================
# query_resolution — transparence du moteur de décision
# =============================================================================

class TestQueryResolutionInResponse:
    """Vérifie que la résolution de stratégie est correctement exposée dans la réponse.

    SearchPropertyUsecase.execute() est mocké pour retourner une résolution préconstruite.

    Symfony équivalent : assertJsonContains(['queryResolution' => ['strategy' => 'sql_only']])
    """

    async def test_query_resolution_is_a_dict(self, client: AsyncClient, mocker):
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(search_results=[])),
        )
        data = (await client.get("/properties/search?q=Maison Paris")).json()
        assert isinstance(data["query_resolution"], dict)

    async def test_query_resolution_has_required_keys(self, client: AsyncClient, mocker):
        """query_resolution expose : strategy, has_structured_filters, has_semantic_terms, reason."""
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(search_results=[])),
        )
        data = (await client.get("/properties/search?q=Maison Paris")).json()
        resolution = data["query_resolution"]

        assert "strategy" in resolution
        assert "has_structured_filters" in resolution
        assert "has_semantic_terms" in resolution
        assert "reason" in resolution

    async def test_structured_query_resolves_to_sql_only(self, client: AsyncClient, mocker):
        """Mock retourne une résolution sql_only → vérifié dans la réponse JSON."""
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(search_results=[])),
        )
        data = (await client.get("/properties/search?q=Maison a Paris")).json()
        resolution = data["query_resolution"]

        assert resolution["strategy"] == "sql_only"
        assert resolution["has_structured_filters"] is True
        assert resolution["has_semantic_terms"] is False

    async def test_semantic_resolution_exposed_in_response(self, client: AsyncClient, mocker):
        """Mock retourne une résolution semantic_only → vérifié dans la réponse JSON."""
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(
                search_results=[],
                total=0,
                resolution=QueryResolution(
                    strategy=QueryStrategy.semantic_only,
                    has_structured_filters=False,
                    has_semantic_terms=True,
                    reason="test: semantic_terms only → semantic_only",
                ),
            )),
        )
        data = (await client.get("/properties/search?q=bonjour")).json()
        resolution = data["query_resolution"]

        assert resolution["strategy"] == "semantic_only"
        assert resolution["has_structured_filters"] is False
        assert resolution["has_semantic_terms"] is True

    async def test_resolution_reason_is_a_string(self, client: AsyncClient, mocker):
        """reason explique pourquoi cette stratégie a été choisie."""
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(search_results=[])),
        )
        data = (await client.get("/properties/search?q=Maison Paris")).json()
        assert isinstance(data["query_resolution"]["reason"], str)
        assert len(data["query_resolution"]["reason"]) > 0


# =============================================================================
# Validation des paramètres HTTP
# =============================================================================

class TestQueryParamValidation:
    async def test_missing_q_returns_422(self, client: AsyncClient):
        """q est obligatoire (Query(...)). Sans q → FastAPI retourne 422 automatiquement.

        Symfony équivalent :
            throw new BadRequestHttpException('q is required');
        FastAPI le fait sans code — juste la déclaration du paramètre suffit.
        """
        response = await client.get("/properties/search")
        assert response.status_code == 422

    async def test_empty_q_returns_422(self, client: AsyncClient):
        """min_length=1 : une chaîne vide est rejetée par FastAPI avant d'appeler l'endpoint."""
        response = await client.get("/properties/search?q=")
        assert response.status_code == 422

    async def test_422_error_mentions_q_field(self, client: AsyncClient):
        """Le corps de l'erreur 422 identifie le champ manquant."""
        data = (await client.get("/properties/search")).json()
        error_fields = [e["loc"] for e in data["detail"]]
        assert any("q" in loc for loc in error_fields)


# =============================================================================
# Validation des paramètres de pagination
# =============================================================================

class TestPaginationParamValidation:
    """FastAPI valide ge=1 sur page et ge=1, le=100 sur per_page automatiquement."""

    async def test_page_0_returns_422(self, client: AsyncClient):
        """page=0 → ge=1 non respecté → 422."""
        response = await client.get("/properties/search?q=Paris&page=0")
        assert response.status_code == 422

    async def test_page_negative_returns_422(self, client: AsyncClient):
        response = await client.get("/properties/search?q=Paris&page=-1")
        assert response.status_code == 422

    async def test_per_page_0_returns_422(self, client: AsyncClient):
        response = await client.get("/properties/search?q=Paris&per_page=0")
        assert response.status_code == 422

    async def test_per_page_101_returns_422(self, client: AsyncClient):
        """per_page=101 → le=100 non respecté → 422."""
        response = await client.get("/properties/search?q=Paris&per_page=101")
        assert response.status_code == 422

    async def test_per_page_1_is_valid(self, client: AsyncClient, mocker):
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result()),
        )
        response = await client.get("/properties/search?q=Paris&per_page=1")
        assert response.status_code == 200

    async def test_per_page_100_is_valid(self, client: AsyncClient, mocker):
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result()),
        )
        response = await client.get("/properties/search?q=Paris&per_page=100")
        assert response.status_code == 200

    async def test_page_1_is_valid(self, client: AsyncClient, mocker):
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result()),
        )
        response = await client.get("/properties/search?q=Paris&page=1")
        assert response.status_code == 200


# =============================================================================
# Résultats vides
# =============================================================================

class TestEmptyResults:
    async def test_no_results_returns_200(self, client: AsyncClient, mocker):
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(search_results=[], total=0)),
        )
        response = await client.get("/properties/search?q=bonjour")
        assert response.status_code == 200

    async def test_no_results_count_is_zero(self, client: AsyncClient, mocker):
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(search_results=[], total=0)),
        )
        data = (await client.get("/properties/search?q=bonjour")).json()
        assert data["count"] == 0
        assert data["results"] == []

    async def test_no_results_total_pages_is_1(self, client: AsyncClient, mocker):
        mocker.patch(
            "app.adapters.controllers.property_search.SearchProperty.execute",
            new=AsyncMock(return_value=_make_usecase_result(search_results=[], total=0)),
        )
        data = (await client.get("/properties/search?q=bonjour")).json()
        assert data["total_pages"] == 1
