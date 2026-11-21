"""Snapshot paths, IST clock and metadata helpers for the daily data refresh (Phase 7).

A *snapshot* is the set of files the app serves from:
    data/vectorstore/   TF-IDF + BM25 artifacts and corpus.json
    data/chroma/        ChromaDB persistent store
    data/metadata.json  run metadata (generated_at, scrape_date, run_id, ...)

The refresh workflow builds a *staging* snapshot next to the live one, validates it,
then promotes it. `data/metadata.json` is always replaced last, so a reader that sees a
new `generated_at` can rely on the index files already being in place.
"""

import json
import os
import shutil
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.config import settings

# India has no DST, so a fixed offset is exact and avoids needing tzdata on Windows.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")

LIVE_CHROMA_PATH = "data/chroma"
LIVE_VECTORSTORE_PATH = "data/vectorstore"
LIVE_METADATA_PATH = "data/metadata.json"

STAGING_CHROMA_PATH = "data/chroma_staging"
STAGING_VECTORSTORE_PATH = "data/vectorstore_staging"
STAGING_METADATA_PATH = "data/metadata_staging.json"
STAGING_COLLECTION = "mf_faq_staging"
VALIDATION_MARKER_PATH = "data/validation_staging.json"

SNAPSHOT_BRANCH = "data-snapshot"
UNKNOWN_DATE = "unknown"


def ist_now() -> datetime:
    return datetime.now(IST)


def ist_today() -> str:
    """Today's date in IST as YYYY-MM-DD (the run date stamped on every chunk)."""
    return ist_now().strftime("%Y-%m-%d")


# ------------------------------------------------------------------------------
# Metadata
# ------------------------------------------------------------------------------
def read_metadata(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Reads a metadata JSON file; returns None if it is missing or unreadable."""
    path = path or settings.data_metadata_path
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


_cache: Dict[str, Any] = {}
_cache_lock = threading.Lock()


def cached_metadata(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Like read_metadata, but re-reads the file only when it changes on disk."""
    path = path or settings.data_metadata_path
    try:
        st = os.stat(path)
    except OSError:
        return None
    # write_json_atomic always creates a new file, so the inode changes even if mtime/size collide
    mtime = (st.st_mtime_ns, st.st_size, st.st_ino)
    with _cache_lock:
        hit = _cache.get(path)
        if hit and hit[0] == mtime:
            return hit[1]
    data = read_metadata(path)
    with _cache_lock:
        _cache[path] = (mtime, data)
    return data


def current_scrape_date() -> str:
    """Scrape date of the live snapshot, used wherever a chunk lacks its own date."""
    for path in (settings.data_metadata_path, os.path.join(settings.vectorstore_path, "metadata.json")):
        meta = cached_metadata(path)
        if meta and meta.get("scrape_date"):
            return str(meta["scrape_date"])
    return UNKNOWN_DATE


def snapshot_version(path: Optional[str] = None) -> Optional[str]:
    """Identifies a snapshot: `generated_at`, or `scrape_date` for pre-Phase-7 metadata."""
    meta = cached_metadata(path)
    if not meta:
        return None
    return str(meta.get("generated_at") or meta.get("scrape_date") or "") or None


def append_summary(path: Optional[str], markdown: str) -> None:
    """Appends markdown to a job summary file (e.g. $GITHUB_STEP_SUMMARY); no-op without a path."""
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(markdown.rstrip() + "\n\n")


def md_table(headers, rows) -> str:
    """Renders a small GitHub-flavoured markdown table."""
    def cell(v):
        return ("—" if v is None or v == "" else str(v)).replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


# ------------------------------------------------------------------------------
# Atomic file operations
# ------------------------------------------------------------------------------
def write_json_atomic(path: str, data: Dict[str, Any]) -> None:
    """Writes JSON to a temp file in the same directory, then renames it into place."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    tmp = os.path.join(directory, f".{os.path.basename(path)}.tmp-{uuid.uuid4().hex[:8]}")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _rename_with_retry(src: str, dst: str, retries: int = 5) -> None:
    # Windows refuses to rename a directory while another process has a file in it open;
    # these locks are usually brief (an in-flight read), so retry before giving up.
    for attempt in range(retries):
        try:
            os.rename(src, dst)
            return
        except PermissionError:
            if attempt == retries - 1:
                raise
            time.sleep(0.5 * (attempt + 1))


def replace_dir(src: str, dst: str) -> None:
    """Replaces directory `dst` with `src` (same filesystem) using two renames.

    The old directory is moved aside first and restored if the second rename fails,
    so `dst` is never left half-written. `src` no longer exists afterwards.
    """
    src, dst = os.path.normpath(src), os.path.normpath(dst)
    if not os.path.isdir(src):
        raise FileNotFoundError(f"Snapshot directory not found: {src}")
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)

    backup = None
    if os.path.exists(dst):
        backup = f"{dst}.old-{uuid.uuid4().hex[:8]}"
        _rename_with_retry(dst, backup)
    try:
        _rename_with_retry(src, dst)
    except Exception:
        if backup:
            os.rename(backup, dst)
        raise
    if backup:
        shutil.rmtree(backup, ignore_errors=True)
