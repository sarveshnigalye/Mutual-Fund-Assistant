"""Admin endpoints for hosted deployments (Railway): pull a new data snapshot without a redeploy.

    POST /api/admin/refresh-data   — called by the daily-data-refresh workflow after it publishes
    GET  /api/admin/data-status    — what is live, what is loaded, how the last sync went

Both require `Authorization: Bearer <REFRESH_TOKEN>`. With REFRESH_TOKEN unset the endpoints do not
exist (404), so a local or misconfigured deployment never exposes them.
"""

import hmac
import logging
import threading
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.ingestion import snapshot, sync

logger = logging.getLogger("api.admin")
router = APIRouter(prefix="/api/admin", tags=["Admin"])


def require_refresh_token(authorization: Optional[str] = Header(default=None)) -> None:
    expected = settings.refresh_token or ""
    if not expected:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.strip().encode(), expected.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _live_summary() -> dict:
    meta = snapshot.read_metadata(snapshot.live_metadata_path()) or {}
    return {key: meta.get(key) for key in ("generated_at", "scrape_date", "run_id", "total_chunks")}


@router.post("/refresh-data", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_refresh_token)])
def refresh_data(force: bool = False):
    """Starts a background sync from SNAPSHOT_REPO@SNAPSHOT_BRANCH; the retriever hot-reloads after it."""
    if not settings.snapshot_repo:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SNAPSHOT_REPO is not configured.")
    if sync.is_running():
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED,
                            content={"status": "busy", "detail": "A sync is already running.", "live": _live_summary()})
    threading.Thread(target=sync.sync_configured, kwargs={"force": force}, name="snapshot-sync", daemon=True).start()
    logger.info(f"Snapshot sync started (force={force}).")
    return {
        "status": "started",
        "source": f"{settings.snapshot_repo}@{settings.snapshot_branch}",
        "live": _live_summary(),
        "detail": "Poll GET /api/admin/data-status; the index reloads within INDEX_RELOAD_CHECK_SECONDS.",
    }


@router.get("/data-status", dependencies=[Depends(require_refresh_token)])
def data_status():
    from app.core.generator import rag_pipeline  # late import: avoid building the pipeline at import time

    live = snapshot.read_metadata(snapshot.live_metadata_path())
    return {
        "live": _live_summary(),
        "loaded_snapshot": rag_pipeline.retriever.snapshot_version,
        "index_loaded": rag_pipeline.retriever.is_loaded,
        "sync_running": sync.is_running(),
        "last_sync": sync.last_result(),
        "snapshot_source": f"{settings.snapshot_repo}@{settings.snapshot_branch}" if settings.snapshot_repo else None,
        "poll_hours": settings.snapshot_poll_hours,
        "library_mismatches": snapshot.library_mismatches(live),
    }
