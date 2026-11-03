from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import init_db
from app.exercises_catalog import ensure_loaded
from app.routers import auth, brain, profile, training

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    ensure_loaded()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(brain.router)
app.include_router(training.router)

# Exercise demo images (openGym / free-exercise-db); unused by UI this phase.
_exercises_dir = _STATIC_DIR / "exercises"
_exercises_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/exercises", StaticFiles(directory=str(_exercises_dir)), name="exercise_media")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "llm_provider": settings.llm_provider,
        "app": settings.app_name,
    }
