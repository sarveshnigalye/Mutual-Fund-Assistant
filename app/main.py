"""FastAPI application entrypoint for Mutual Fund FAQ Assistant."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

app = FastAPI(
    title="Mutual Fund FAQ Assistant API",
    description="Facts-only Q&A assistant for HDFC Mutual Fund schemes via Groq & ChromaDB",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{settings.streamlit_port}",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["Health"])
def health_check():
    """Health check endpoint confirming service status and active provider."""
    return {
        "status": "healthy",
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "disclaimer": "Facts-only. No investment advice.",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=True)
