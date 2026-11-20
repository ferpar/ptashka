"""FastAPI application entry point.

Run with: uvicorn ptashka.main:app --reload --port 8020
Interactive docs: http://localhost:8020/docs
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ptashka.api.admin import router as admin_router
from ptashka.api.auth import router as auth_router
from ptashka.api.boards import router as boards_router
from ptashka.api.lists import router as lists_router

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
app.include_router(boards_router)
app.include_router(lists_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy"}
