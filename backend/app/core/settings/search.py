from pydantic import BaseModel, Field


class SearchSettings(BaseModel):
    semantic_default_top_k: int = Field(default=10, gt=0)
    hybrid_default_top_k: int = Field(default=20, gt=0)
