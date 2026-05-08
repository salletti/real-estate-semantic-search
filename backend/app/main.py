import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.controllers.property_search import router as property_search_router
from app.core.config import settings

app = FastAPI(
    title="Playiad AI Copilot",
    description="Natural Language Real Estate Query Engine",
    version="0.1.0",
    debug=settings.app_debug,
)

_extra_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", *_extra_origins],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
#
# include_router() monte le router dans l'application.
# Toutes les routes définies dans property_search_router deviennent actives.
app.include_router(property_search_router)


@app.get("/health", tags=["ops"])
async def health() -> dict:
    return {"status": "ok", "env": settings.app_env}
