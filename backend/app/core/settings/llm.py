from pydantic import BaseModel, Field


class LLMSettings(BaseModel):
    use_llm: bool = False
    api_key: str = ""
    base_url: str = Field(default="https://api.groq.com/openai/v1", min_length=1)
    model: str = Field(default="llama-3.1-8b-instant", min_length=1)
    timeout_seconds: float = Field(default=10.0, gt=0)
    max_tokens: int = Field(default=512, gt=0)
    temperature: float = Field(default=0.0, ge=0, le=2)
    seed: int = Field(default=42, ge=0)
