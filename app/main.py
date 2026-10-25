"""FastAPI application entrypoint for Mutual Fund FAQ Assistant."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.chat.manager import chat_manager
from app.config import settings
from app.core.retriever import MutualFundRetriever

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

    # Warm up Vector Index
    try:
        retriever = MutualFundRetriever()
        if retriever.load():
            logger.info("Vector index loaded successfully.")
        else:
            logger.warning("Vector index not found. Run 'scripts/ingest.py' to populate.")
    except Exception as e:
        logger.warning(f"Vector index warm-up warning: {e}")

    yield

    logger.info("Shutting down Mutual Fund FAQ Assistant API.")


app = FastAPI(
    title="HDFC Mutual Fund FAQ Assistant API",
    description="Facts-only Q&A assistant for HDFC Mutual Fund schemes via Groq & ChromaDB/Hybrid search.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{settings.streamlit_port}",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)


@app.get("/", tags=["Root"])
def root():
    return {
        "message": "Welcome to HDFC Mutual Fund FAQ Assistant API",
        "docs_url": "/docs",
        "health_url": "/api/health",
        "disclaimer": "Facts-only. No investment advice.",
    }


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
