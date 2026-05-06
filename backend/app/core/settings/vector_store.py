from pydantic import BaseModel, Field


class VectorStoreSettings(BaseModel):
    # Cloud mode: set QDRANT_URL + QDRANT_API_KEY (takes precedence over host/port)
    url: str | None = None
    api_key: str | None = None
    # Local/Docker fallback
    host: str = Field(default="qdrant", min_length=1)
    port: int = Field(default=6333, ge=1, le=65535)
    collection_name: str = Field(default="properties", min_length=1)
