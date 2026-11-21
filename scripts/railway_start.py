"""Production launcher for hosted deployments (Railway start command: `python scripts/railway_start.py`).

    python scripts/railway_start.py              # API + web UI (service "api")
    python scripts/railway_start.py streamlit    # Streamlit frontend (service "streamlit")

API mode:
1. Best-effort snapshot sync from SNAPSHOT_REPO (GitHub, no .git needed). Never fatal: if GitHub is
   unreachable the app starts with whatever is already on the volume, and the refresh endpoint /
   poller retries later.
2. uvicorn on [::]:$PORT — on Linux `::` listens on IPv4 and IPv6, which Railway's private network
   needs (0.0.0.0 on Windows, where `::` would be IPv6-only) — without the dev auto-reloader,
   trusting the proxy's X-Forwarded-* headers.

Reading PORT here (instead of `--port $PORT` in the start command) avoids depending on whether the
platform expands shell variables in start commands.
"""

import logging
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
if __name__ == "__main__":
    os.chdir(ROOT)  # .env, frontend/ and relative data paths resolve from the repo root

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("railway_start")


def port() -> int:
    return int(os.environ.get("PORT") or 8000)


def host() -> str:
    # `::` is dual-stack (IPv4 + IPv6) on Linux — what Railway's private network needs. Windows makes
    # IPv6 sockets IPv6-only, so `::` would silently drop IPv4 there; use 0.0.0.0 for local runs.
    return os.environ.get("HOST") or ("0.0.0.0" if os.name == "nt" else "::")


def ensure_data_dirs() -> None:
    from app.config import settings

    for path in (settings.chat_db_path, settings.data_metadata_path, settings.vectorstore_path):
        parent = os.path.dirname(os.path.abspath(path)) if os.path.splitext(path)[1] else os.path.abspath(path)
        os.makedirs(parent, exist_ok=True)


def startup_sync() -> None:
    from app.config import settings

    if not settings.snapshot_repo:
        logger.info("SNAPSHOT_REPO not set: skipping startup snapshot sync.")
        return
    try:
        from app.ingestion import sync

        result = sync.sync_configured()
        log = logger.error if result.status == "failed" else logger.info
        log(f"Startup snapshot sync: {result.status} — {result.message}")
    except Exception as e:  # never block the app from starting
        logger.exception(f"Startup snapshot sync crashed ({e}); starting with the data on disk.")


def run_api() -> None:
    import uvicorn

    ensure_data_dirs()
    startup_sync()
    logger.info(f"Starting API on [{host()}]:{port()}")
    uvicorn.run(
        "app.main:app",
        host=host(),
        port=port(),
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="*",  # Railway's edge proxy sets X-Forwarded-For / -Proto
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )


def run_streamlit() -> None:
    cmd = [
        sys.executable, "-m", "streamlit", "run", os.path.join("frontend", "streamlit_app.py"),
        "--server.port", str(port()),
        "--server.address", os.environ.get("HOST") or "0.0.0.0",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
    ]
    logger.info(f"Starting Streamlit on port {port()} (API_URL={os.environ.get('API_URL', '<default>')})")
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "api"
    if mode == "api":
        run_api()
    elif mode == "streamlit":
        run_streamlit()
    else:
        sys.exit(f"Unknown mode '{mode}' (expected: api | streamlit)")
