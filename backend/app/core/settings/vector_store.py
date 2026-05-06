from pydantic import BaseModel, Field


class VectorStoreSettings(BaseModel):
    host: str = Field(default="qdrant", min_length=1)
    port: int = Field(default=6333, ge=1, le=65535)
    collection_name: str = Field(default="properties", min_length=1)
