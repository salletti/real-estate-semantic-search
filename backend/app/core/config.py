from functools import cached_property, lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import SEMANTIC_SEARCH_QUERY_PREFIX
from app.core.settings import (
    EmbeddingSettings,
    LLMSettings,
    SearchSettings,
    VectorStoreSettings,
)


ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    app_env: str = "development"
    app_debug: bool = True
    secret_key: str

    database_url: str

    # Vector store — flat env-backed fields kept for backward compatibility
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "properties"

    # Groq — flat env-backed fields kept for backward compatibility
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.1-8b-instant"
    groq_timeout_seconds: float = 10.0
    groq_max_tokens: int = 512
    groq_temperature: float = 0.0
    groq_seed: int = 42

    # Intent parser — USE_LLM=true active parse_intent_using_llm (rule + LLM hybrid)
    use_llm: bool = False

    # Embeddings — flat env-backed fields kept for backward compatibility
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Search strategy tuning — flat env-backed fields kept for backward compatibility
    semantic_default_top_k: int = 10
    hybrid_default_top_k: int = 20

    @cached_property
    def llm(self) -> LLMSettings:
        return LLMSettings(
            use_llm=self.use_llm,
            api_key=self.groq_api_key,
            base_url=self.groq_base_url,
            model=self.groq_model,
            timeout_seconds=self.groq_timeout_seconds,
            max_tokens=self.groq_max_tokens,
            temperature=self.groq_temperature,
            seed=self.groq_seed,
        )

    @cached_property
    def embeddings(self) -> EmbeddingSettings:
        return EmbeddingSettings(model_name=self.embedding_model_name)

    @cached_property
    def search(self) -> SearchSettings:
        return SearchSettings(
            semantic_default_top_k=self.semantic_default_top_k,
            hybrid_default_top_k=self.hybrid_default_top_k,
        )

    @cached_property
    def vector_store(self) -> VectorStoreSettings:
        return VectorStoreSettings(
            host=self.qdrant_host,
            port=self.qdrant_port,
            collection_name=self.qdrant_collection_name,
        )

    @property
    def search_query_prefix(self) -> str:
        return SEMANTIC_SEARCH_QUERY_PREFIX

    @model_validator(mode="after")
    def validate_nested_settings(self) -> "Settings":
        # Eagerly build the modular settings so invalid env values fail at startup.
        self.llm
        self.embeddings
        self.search
        self.vector_store
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
