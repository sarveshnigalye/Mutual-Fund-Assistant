"""Launcher for FastAPI backend server."""

import os
import sys
import uvicorn

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.config import settings

if __name__ == "__main__":
    print(f"🚀 Launching FastAPI server on http://{settings.api_host}:{settings.api_port}...")
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=True)

