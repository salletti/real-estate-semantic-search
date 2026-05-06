import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.core.constants import SEMANTIC_SEARCH_QUERY_PREFIX


class TestSettingsValidation:
    def test_valid_settings_exposes_modular_views(self):
        settings = Settings(
            secret_key="test-secret",
            database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
        )

        assert settings.llm.timeout_seconds == 10.0
        assert settings.embeddings.model_name == "sentence-transformers/all-MiniLM-L6-v2"
        assert settings.search.semantic_default_top_k == 10
        assert settings.vector_store.port == 6333
        assert settings.search_query_prefix == SEMANTIC_SEARCH_QUERY_PREFIX

    @pytest.mark.parametrize(
        ("field_name", "value", "expected_fragment"),
        [
            ("groq_timeout_seconds", 0, "greater than 0"),
            ("groq_max_tokens", 0, "greater than 0"),
            ("groq_temperature", 3, "less than or equal to 2"),
            ("semantic_default_top_k", 0, "greater than 0"),
            ("hybrid_default_top_k", 0, "greater than 0"),
            ("qdrant_port", 70000, "less than or equal to 65535"),
            ("qdrant_port", 0, "greater than or equal to 1"),
            ("embedding_model_name", "", "at least 1 character"),
        ],
    )
    def test_invalid_settings_raise_validation_error(self, field_name, value, expected_fragment):
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                secret_key="test-secret",
                database_url="postgresql+asyncpg://user:pass@localhost:5432/db",
                **{field_name: value},
            )

        assert expected_fragment in str(exc_info.value)


class TestGetSettingsCache:
    def test_get_settings_returns_cached_instance(self, monkeypatch):
        get_settings.cache_clear()
        monkeypatch.setenv("SECRET_KEY", "cache-secret")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")

        first = get_settings()
        second = get_settings()

        assert first is second

        get_settings.cache_clear()

    def test_cache_clear_reloads_environment(self, monkeypatch):
        get_settings.cache_clear()
        monkeypatch.setenv("SECRET_KEY", "first-secret")
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")

        first = get_settings()
        assert first.secret_key == "first-secret"

        monkeypatch.setenv("SECRET_KEY", "second-secret")
        get_settings.cache_clear()

        second = get_settings()
        assert second.secret_key == "second-secret"

        get_settings.cache_clear()
