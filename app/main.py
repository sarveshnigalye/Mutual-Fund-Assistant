"""FastAPI application entrypoint for Mutual Fund FAQ Assistant."""

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.limits import RequestLimitsMiddleware
from app.api.routes import router
from app.chat.manager import chat_manager
from app.config import settings
from app.core.rag_pipeline import rag_pipeline
from app.ingestion import sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for warming up models and database connections."""
    logger.info("Initializing Mutual Fund FAQ Assistant API...")

    # Warm up SQLite database schema
    try:
        _ = chat_manager.list_threads()
        logger.info("Chat database initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize chat database: {e}")

    # Warm up the vector index used by the shared RAG pipeline
    try:
        if rag_pipeline.retriever.load():
            logger.info("Vector index loaded successfully.")
        else:
            logger.warning("Vector index not found. Run 'scripts/ingest.py' to populate.")
    except Exception as e:
        logger.warning(f"Vector index warm-up warning: {e}")

    # Safety net for hosted deployments: if the workflow's refresh call was missed, pick up the
    # published snapshot on a timer (SNAPSHOT_POLL_HOURS; 0 = off). Cheap when nothing changed:
    # one small GitHub request for metadata.json.
    poller = None
    if settings.snapshot_repo and settings.snapshot_poll_hours > 0:
        poller = asyncio.create_task(_poll_snapshots(settings.snapshot_poll_hours * 3600))
        logger.info(f"Snapshot poll every {settings.snapshot_poll_hours} h from {settings.snapshot_repo}.")

    yield

    if poller:
        poller.cancel()
    logger.info("Shutting down Mutual Fund FAQ Assistant API.")


async def _poll_snapshots(interval_seconds: float) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await asyncio.to_thread(sync.sync_configured)
        except Exception as e:  # never let the poller die
            logger.error(f"Snapshot poll failed: {e}")


app = FastAPI(
    title="HDFC Mutual Fund FAQ Assistant API",
    description="Facts-only Q&A assistant for HDFC Mutual Fund schemes via Groq & ChromaDB/Hybrid search.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted({
        f"http://localhost:{settings.streamlit_port}",
        f"http://127.0.0.1:{settings.streamlit_port}",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    }),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import os
from fastapi.responses import FileResponse, JSONResponse
from fastapi import Request

# Body-size limit + per-IP rate limit on /api/chat (RATE_LIMIT_PER_MINUTE, 0 = off)
app.add_middleware(RequestLimitsMiddleware)

# Include API routes
app.include_router(router)
app.include_router(admin_router)  # /api/admin/* — 404 unless REFRESH_TOKEN is set


@app.get("/", tags=["Root"])
def root(request: Request):
    accept_header = request.headers.get("accept", "")
    index_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html"))
    if "text/html" in accept_header and os.path.exists(index_path):
        return FileResponse(index_path)

    return JSONResponse({
        "message": "Welcome to HDFC Mutual Fund FAQ Assistant API",
        "docs_url": "/docs",
        "health_url": "/api/health",
        "ui_url": "/app",
        "disclaimer": "Facts-only. No investment advice.",
    })


@app.get("/app", tags=["UI"])
def serve_ui():
    index_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html"))
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"error": "UI file not found"}, status_code=404)


@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "ok",
        "service": "HDFC Mutual Fund FAQ Assistant API",
        "version": "1.0.0",
        "disclaimer": "Facts-only, non-advisory assistant.",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=True)
