"""Install a published data snapshot on this host (Phase 7.9 + Railway deployment, D1.2).

Three sources, one install path:
    sync_from_github(repo, branch)  — download the data-snapshot branch tarball over HTTPS
                                      (hosted deployments such as Railway have no .git checkout)
    sync_from_git(remote, branch)   — `git fetch` + `git archive` in a repo checkout
    sync_from_dir(path)             — an unzipped workflow artifact / any dir containing data/

`install()` swaps ChromaDB first (the swap that can fail on Windows file locks — nothing live has
changed if it does), then the vectorstore, and writes metadata.json last: that write is what the
running retriever's hot reload watches for.
"""

import io
import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from app.ingestion import snapshot

logger = logging.getLogger("ingestion.sync")

# Overridable for GitHub Enterprise or an end-to-end test against a local stand-in.
GITHUB_API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
HTTP_TIMEOUT_SECONDS = 60
_lock = threading.Lock()
_last_result: Optional["SyncResult"] = None


class SyncError(RuntimeError):
    """The snapshot could not be installed; the live data is unchanged."""


@dataclass
class SyncResult:
    status: str  # "installed" | "up_to_date" | "failed" | "busy"
    message: str
    previous: Optional[str] = None  # generated_at before
    current: Optional[str] = None  # generated_at after (or of the snapshot that failed)
    scrape_date: Optional[str] = None
    total_chunks: Optional[int] = None
    finished_at: str = field(default_factory=lambda: snapshot.ist_now().isoformat(timespec="seconds"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def last_result() -> Optional[Dict[str, Any]]:
    return _last_result.to_dict() if _last_result else None


def is_running() -> bool:
    return _lock.locked()


# ------------------------------------------------------------------------------
# Install
# ------------------------------------------------------------------------------
def _safe_extract(tar: tarfile.TarFile, dest: str) -> None:
    dest_abs = os.path.abspath(dest)
    for member in tar.getmembers():
        target = os.path.abspath(os.path.join(dest_abs, member.name))
        if not (target == dest_abs or target.startswith(dest_abs + os.sep)) or member.issym() or member.islnk():
            raise SyncError(f"Refusing unsafe path in snapshot archive: {member.name}")
    tar.extractall(dest_abs)


def _snapshot_root(extracted: str) -> str:
    """Directory that contains data/ — GitHub tarballs wrap everything in '<owner>-<repo>-<sha>/'."""
    if os.path.isdir(os.path.join(extracted, "data")):
        return extracted
    entries = [e for e in os.listdir(extracted) if os.path.isdir(os.path.join(extracted, e))]
    if len(entries) == 1 and os.path.isdir(os.path.join(extracted, entries[0], "data")):
        return os.path.join(extracted, entries[0])
    raise SyncError("Snapshot archive has no data/ directory.")


def install(src_root: str) -> Dict[str, Any]:
    """Installs <src_root>/data/{chroma,vectorstore,metadata.json} into this host's live paths."""
    src_data = os.path.join(src_root, "data")
    new_meta = snapshot.read_metadata(os.path.join(src_data, "metadata.json"))
    if not new_meta:
        raise SyncError(f"Snapshot has no readable data/metadata.json under {src_root}.")
    if not os.path.isfile(os.path.join(src_data, "vectorstore", "corpus.json")):
        raise SyncError("Snapshot has no data/vectorstore/corpus.json.")

    if os.path.isdir(os.path.join(src_data, "chroma")):
        try:
            snapshot.replace_dir(os.path.join(src_data, "chroma"), snapshot.live_chroma_path())
        except PermissionError as e:
            raise SyncError(
                f"Could not replace {snapshot.live_chroma_path()} ({e}); nothing was changed. "
                "Stop the process holding ChromaDB open (e.g. a backend with VECTOR_DB_PROVIDER=chromadb) "
                "and sync again."
            )
    snapshot.replace_dir(os.path.join(src_data, "vectorstore"), snapshot.live_vectorstore_path())
    snapshot.write_json_atomic(snapshot.live_metadata_path(), new_meta)  # last: triggers the reload

    mismatches = snapshot.library_mismatches(new_meta)
    if mismatches:
        logger.warning(f"Snapshot built with different library versions (built, installed): {mismatches}")
    return new_meta


def _new_temp_dir() -> str:
    root = snapshot.live_data_root()  # same disk as the live paths, so the swaps are renames
    os.makedirs(root, exist_ok=True)
    return tempfile.mkdtemp(prefix=".sync-", dir=root)


def _run(source: str, fetch, force: bool, remote_meta: Optional[Dict[str, Any]] = None) -> SyncResult:
    """Common flow: up-to-date check, fetch into a temp dir, install, record the result."""
    global _last_result
    if not _lock.acquire(blocking=False):
        return SyncResult("busy", "Another sync is already running.")
    current = snapshot.read_metadata(snapshot.live_metadata_path()) or {}
    previous = current.get("generated_at") or current.get("scrape_date")
    tmp = None
    try:
        if remote_meta and not force and remote_meta.get("generated_at") == current.get("generated_at"):
            result = SyncResult("up_to_date", f"Already up to date ({source}).", previous, previous,
                                current.get("scrape_date"), current.get("total_chunks"))
        else:
            tmp = _new_temp_dir()
            src_root = fetch(tmp)
            incoming = snapshot.read_metadata(os.path.join(src_root, "data", "metadata.json")) or {}
            if not force and incoming.get("generated_at") and incoming.get("generated_at") == current.get("generated_at"):
                result = SyncResult("up_to_date", f"Already up to date ({source}).", previous, previous,
                                    current.get("scrape_date"), current.get("total_chunks"))
            else:
                meta = install(src_root)
                result = SyncResult(
                    "installed",
                    f"Installed snapshot {meta.get('generated_at')} from {source}.",
                    previous, meta.get("generated_at"), meta.get("scrape_date"), meta.get("total_chunks"),
                )
    except Exception as e:  # SyncError, network, archive and filesystem errors alike
        result = SyncResult("failed", f"{type(e).__name__}: {e}", previous, previous,
                            current.get("scrape_date"), current.get("total_chunks"))
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        _lock.release()
    (logger.info if result.status != "failed" else logger.error)(f"Snapshot sync: {result.message}")
    _last_result = result
    return result


# ------------------------------------------------------------------------------
# Sources
# ------------------------------------------------------------------------------
def _github_request(url: str, token: Optional[str], accept: str) -> urllib.request.Request:
    headers = {"Accept": accept, "User-Agent": "mf-faq-snapshot-sync", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def fetch_github_metadata(repo: str, branch: str, token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Reads data/metadata.json of the snapshot branch (one small request) — None if unavailable."""
    url = f"{GITHUB_API}/repos/{repo}/contents/{snapshot.SNAPSHOT_METADATA_PATH}?ref={branch}"
    try:
        with urllib.request.urlopen(_github_request(url, token, "application/vnd.github.raw+json"),
                                    timeout=HTTP_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError) as e:
        logger.warning(f"Could not read remote snapshot metadata for {repo}@{branch}: {e}")
        return None


def download_github_snapshot(repo: str, branch: str, token: Optional[str], dest: str) -> str:
    """Downloads the branch tarball into `dest`; returns the directory that contains data/."""
    url = f"{GITHUB_API}/repos/{repo}/tarball/{branch}"
    try:
        with urllib.request.urlopen(_github_request(url, token, "application/vnd.github+json"),
                                    timeout=HTTP_TIMEOUT_SECONDS) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as e:
        hint = " (private repo? set SNAPSHOT_TOKEN)" if e.code in (401, 403, 404) and not token else ""
        raise SyncError(f"GitHub returned {e.code} for {repo}@{branch}{hint}.") from e
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as tar:
        _safe_extract(tar, dest)
    return _snapshot_root(dest)


def sync_from_github(repo: str, branch: str = snapshot.SNAPSHOT_BRANCH, token: Optional[str] = None,
                     force: bool = False) -> SyncResult:
    if not repo:
        return SyncResult("failed", "No repository configured (SNAPSHOT_REPO).")
    remote_meta = None if force else fetch_github_metadata(repo, branch, token)
    return _run(f"github:{repo}@{branch}",
                lambda tmp: download_github_snapshot(repo, branch, token, tmp), force, remote_meta)


def sync_from_git(remote: str = "origin", branch: str = snapshot.SNAPSHOT_BRANCH, force: bool = False,
                  cwd: Optional[str] = None) -> SyncResult:
    def fetch(tmp: str) -> str:
        ref = f"refs/remotes/{remote}/{branch}"

        def git(args):
            proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
            if proc.returncode != 0:
                raise SyncError(f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
            return proc.stdout

        git(["fetch", "--depth=1", remote, f"+refs/heads/{branch}:{ref}"])
        with tarfile.open(fileobj=io.BytesIO(git(["archive", "--format=tar", ref, "data"])), mode="r:") as tar:
            _safe_extract(tar, tmp)
        return _snapshot_root(tmp)

    return _run(f"git:{remote}/{branch}", fetch, force)


def sync_from_dir(src_dir: str, force: bool = False) -> SyncResult:
    def fetch(tmp: str) -> str:
        # never consume the caller's directory: copy it next to the live paths first
        shutil.copytree(os.path.join(_snapshot_root(os.path.abspath(src_dir)), "data"), os.path.join(tmp, "data"))
        return tmp

    return _run(f"dir:{src_dir}", fetch, force)


def sync_configured(force: bool = False) -> SyncResult:
    """Syncs from the GitHub repo configured via SNAPSHOT_REPO / SNAPSHOT_BRANCH / SNAPSHOT_TOKEN."""
    from app.config import settings

    return sync_from_github(settings.snapshot_repo, settings.snapshot_branch or snapshot.SNAPSHOT_BRANCH,
                            settings.snapshot_token or None, force=force)
