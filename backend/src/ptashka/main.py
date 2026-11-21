"""FastAPI application entry point.

Run with: uvicorn ptashka.main:app --reload --port 8020
Interactive docs: http://localhost:8020/docs
"""

import os

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from ptashka.api.activity import router as activity_router
from ptashka.api.admin import router as admin_router
from ptashka.api.auth import router as auth_router
from ptashka.api.boards import router as boards_router
from ptashka.api.cards import router as cards_router
from ptashka.api.checklist import router as checklist_router
from ptashka.api.comments import router as comments_router
from ptashka.api.labels import router as labels_router
from ptashka.api.lists import router as lists_router
from ptashka.api.tokens import router as tokens_router
from ptashka.auth.jwt import JWT_SECRET_KEY
from ptashka.config import ENVIRONMENT, validate_settings
from ptashka.db.database import DbSession

# Refuse to start with unsafe production settings (see config.py), before serving anything.
validate_settings(ENVIRONMENT, JWT_SECRET_KEY)

app = FastAPI(title="Ptashka API", description="Trello-like task manager", version="0.1.0")

# Lets the Vite dev server (another origin) call the API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3020,http://localhost:3021").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(tokens_router)
app.include_router(boards_router)
app.include_router(lists_router)
app.include_router(cards_router)
app.include_router(labels_router)
app.include_router(checklist_router)
app.include_router(comments_router)
app.include_router(activity_router)


@app.exception_handler(StaleDataError)
def concurrent_modification(_request: Request, _exc: StaleDataError) -> JSONResponse:
    """Safety net for optimistic locking: a row's version changed between our read and our write
    (e.g. two requests moving the same card at once). The unit of work has already rolled back;
    tell the client to reload instead of failing with a 500."""
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "Modified concurrently by another request; reload and retry"},
    )


@app.get("/health", response_model=None)
def health_check(db: DbSession) -> dict[str, str] | JSONResponse:
    """For Docker/Coolify healthchecks: healthy only if the database answers too.

    A deploy whose app starts but can't reach its database is a failed deploy; saying "healthy"
    there would let it replace a working version.
    """
    try:
        db.execute(text("SELECT 1"))
    except OperationalError:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"status": "unhealthy", "database": "unreachable"})
    return {"status": "healthy", "database": "ok"}
