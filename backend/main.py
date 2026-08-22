"""
Accessible Form Assistant — API entrypoint.

Run locally:
    python -m uvicorn main:app --reload --port 8000
"""

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from dotenv import load_dotenv

load_dotenv()

from routes import chat

app = FastAPI(
    title="Accessible Form Assistant",
    description="Conversational form filling for users facing visual, cognitive or literacy barriers.",
    version="1.0.0",
)

allowed_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(chat.router)


@app.get("/health")
def health() -> dict:
    """Uptime probe. Reports whether the LLM key is configured without exposing it."""
    return {
        "status": "ok",
        "llm_configured": bool(os.environ.get("GROQ_API_KEY")),
    }


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/")
    def serve_index() -> FileResponse:
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app.get("/{path:path}")
    def serve_spa(path: str) -> FileResponse:
        candidate = os.path.join(STATIC_DIR, path)
        if path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

else:

    @app.get("/")
    def root() -> dict:
        return {"service": "Accessible Form Assistant", "docs": "/docs"}
