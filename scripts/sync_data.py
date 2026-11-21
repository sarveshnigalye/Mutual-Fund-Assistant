"""Pull the latest published snapshot onto this app host (Phase 7.9).

    python scripts/sync_data.py                       # fetch origin/data-snapshot and install it
    python scripts/sync_data.py --from-dir ./artifact # install from an unzipped workflow artifact
    python scripts/sync_data.py --force               # reinstall even if already current

data/vectorstore and data/chroma are replaced by directory renames from a temp dir on the same
disk, and data/metadata.json is replaced last. A running backend notices the new
`generated_at` within INDEX_RELOAD_CHECK_SECONDS (default 60 s) and reloads — no restart.

Schedule it after the daily refresh, e.g. Windows Task Scheduler at 10:45 IST, or cron
`15 5 * * *` (UTC) on Linux.
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
if __name__ == "__main__":
    os.chdir(ROOT)

from app.ingestion import snapshot


def _git(args, binary=False):
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout if binary else proc.stdout.decode("utf-8").strip()


def _safe_extract(tar: tarfile.TarFile, dest: str) -> None:
    dest_abs = os.path.abspath(dest)
    for member in tar.getmembers():
        target = os.path.abspath(os.path.join(dest_abs, member.name))
        if not target.startswith(dest_abs + os.sep) or member.issym() or member.islnk():
            raise SystemExit(f"Refusing unsafe path in snapshot archive: {member.name}")
    tar.extractall(dest_abs)


def fetch_snapshot(remote: str, branch: str, dest: str) -> None:
    """Fetches `remote/branch` (depth 1) and extracts its data/ tree into `dest`."""
    ref = f"refs/remotes/{remote}/{branch}"
    _git(["fetch", "--depth=1", remote, f"+refs/heads/{branch}:{ref}"])
    archive = _git(["archive", "--format=tar", ref, "data"], binary=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        _safe_extract(tar, dest)


def install(src_root: str) -> dict:
    """Installs <src_root>/data/{vectorstore,chroma,metadata.json} into the live paths."""
    src_data = os.path.join(src_root, "data")
    new_meta = snapshot.read_metadata(os.path.join(src_data, "metadata.json"))
    if not new_meta:
        raise SystemExit(f"Snapshot has no readable data/metadata.json under {src_root}.")
    if not os.path.isfile(os.path.join(src_data, "vectorstore", "corpus.json")):
        raise SystemExit("Snapshot has no data/vectorstore/corpus.json.")

    # Chroma first: it is the swap that can fail (Windows locks the sqlite file while a backend with
    # VECTOR_DB_PROVIDER=chromadb runs). If it does, nothing live has changed and we exit non-zero,
    # so the TF-IDF index and ChromaDB never end up on different snapshots.
    if os.path.isdir(os.path.join(src_data, "chroma")):
        try:
            snapshot.replace_dir(os.path.join(src_data, "chroma"), snapshot.LIVE_CHROMA_PATH)
        except PermissionError as e:
            raise SystemExit(
                f"❌ Could not replace {snapshot.LIVE_CHROMA_PATH} ({e}); nothing was changed. "
                "Stop the backend (it holds ChromaDB open) and run sync_data.py again."
            )
    snapshot.replace_dir(os.path.join(src_data, "vectorstore"), snapshot.LIVE_VECTORSTORE_PATH)
    snapshot.write_json_atomic(snapshot.LIVE_METADATA_PATH, new_meta)  # last: triggers the reload
    return new_meta


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--remote", default="origin")
    p.add_argument("--branch", default=snapshot.SNAPSHOT_BRANCH)
    p.add_argument("--from-dir", help="directory that contains data/ (e.g. an unzipped artifact)")
    p.add_argument("--force", action="store_true", help="install even if the snapshot is already current")
    args = p.parse_args(argv)

    current = snapshot.read_metadata(snapshot.LIVE_METADATA_PATH) or {}
    os.makedirs("data", exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".sync-", dir="data")  # same disk as the live paths, so renames work
    try:
        if args.from_dir:
            src_root = os.path.abspath(args.from_dir)
        else:
            fetch_snapshot(args.remote, args.branch, tmp)
            src_root = tmp

        incoming = snapshot.read_metadata(os.path.join(src_root, "data", "metadata.json")) or {}
        if not args.force and incoming.get("generated_at") and incoming.get("generated_at") == current.get("generated_at"):
            print(f"Already up to date: snapshot {current.get('generated_at')} (scrape date {current.get('scrape_date')}).")
            return 0
        if args.from_dir:
            # never consume the caller's directory: copy it next to the live paths first
            shutil.copytree(os.path.join(src_root, "data"), os.path.join(tmp, "data"))
            src_root = tmp

        meta = install(src_root)
        print(f"✅ Installed snapshot {meta.get('generated_at')} — scrape date {meta.get('scrape_date')}, "
              f"run {meta.get('run_id')}, {meta.get('total_chunks')} chunks. "
              f"(previous: {current.get('generated_at') or current.get('scrape_date') or 'none'})")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
