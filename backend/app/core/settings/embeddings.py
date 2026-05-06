from pydantic import BaseModel, Field


class EmbeddingSettings(BaseModel):
    model_name: str = Field(default="sentence-transformers/all-MiniLM-L6-v2", min_length=1)
