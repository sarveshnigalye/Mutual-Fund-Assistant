"""Promote a validated staging index to live and publish it to the `data-snapshot` branch (Phase 7.8).

    python scripts/publish_snapshot.py --branch data-snapshot            # CI
    python scripts/publish_snapshot.py --no-push                         # promote locally only

1. Refuses to run unless data/validation_staging.json says the *same* staging build passed.
2. Renames the staging ChromaDB collection (`mf_faq_staging`) to the live name, then moves
   data/vectorstore_staging → data/vectorstore and data/chroma_staging → data/chroma, and
   writes data/metadata.json last (the signal the app reloads on).
3. Commits data/vectorstore, data/chroma and data/metadata.json as ONE parentless commit and
   force-pushes it to the orphan branch, so the branch never accumulates history (~8 MB, not
   ~3 GB/year). The commit is built with a temporary git index: the checkout is not touched.
"""

import argparse
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
if __name__ == "__main__":
    os.chdir(ROOT)

from app.config import settings
from app.ingestion import snapshot

BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


def _git(args, env=None, input_text=None) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, env=env, input=input_text,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def check_marker(marker_path: str, metadata: dict) -> None:
    marker = snapshot.read_metadata(marker_path)
    if not marker:
        raise SystemExit(f"Refusing to publish: no validation marker at {marker_path}. Run validate_index.py first.")
    if not marker.get("passed"):
        raise SystemExit("Refusing to publish: the validation gate failed for this build.")
    if marker.get("generated_at") != metadata.get("generated_at"):
        raise SystemExit(
            "Refusing to publish: the validation marker is for a different build "
            f"({marker.get('generated_at')} != {metadata.get('generated_at')})."
        )


_RENAME_CODE = """
import sys
sys.path.insert(0, sys.argv[1])
from app.ingestion.chroma_store import CHROMADB_AVAILABLE, ChromaVectorStore
if not CHROMADB_AVAILABLE:
    sys.exit("Staging ChromaDB exists but chromadb is not installed; cannot swap collections.")
store = ChromaVectorStore(persist_directory=sys.argv[2], collection_name=sys.argv[3])
if not store.is_ready() or store.count() == 0:
    sys.exit(f"Staging collection `{sys.argv[3]}` is missing or empty.")
store.rename_collection(sys.argv[4])
print(f"Renamed collection {sys.argv[3]} -> {sys.argv[4]} ({store.count()} chunks)")
"""


def rename_staging_collection(live_collection: str) -> None:
    """Renames the staging collection to the live name in a child process.

    Chroma keeps its SQLite file open for the life of the client; a separate process guarantees
    every handle is closed before the directory is moved (Windows refuses to move open files).
    """
    proc = subprocess.run(
        [sys.executable, "-c", _RENAME_CODE, ROOT, snapshot.STAGING_CHROMA_PATH,
         snapshot.STAGING_COLLECTION, live_collection],
        cwd=ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"Could not swap the ChromaDB collection: {(proc.stderr or proc.stdout).strip()[-800:]}")
    print(proc.stdout.strip())


def check_layout() -> None:
    """Publishing commits the repo-layout paths, so this host must serve from exactly those."""
    expected = {
        "VECTORSTORE_PATH": (snapshot.live_vectorstore_path(), snapshot.SNAPSHOT_VECTORSTORE_PATH),
        "CHROMA_DB_PATH": (snapshot.live_chroma_path(), snapshot.SNAPSHOT_CHROMA_PATH),
        "DATA_METADATA_PATH": (snapshot.live_metadata_path(), snapshot.SNAPSHOT_METADATA_PATH),
    }
    wrong = [f"{k}={live}" for k, (live, layout) in expected.items()
             if os.path.abspath(live) != os.path.abspath(os.path.join(ROOT, layout))]
    if wrong:
        raise SystemExit(f"publish_snapshot.py must run in the repo checkout with default data paths; got {wrong}.")


def promote(live_collection: str) -> dict:
    """Moves the staging build into the live paths. Returns the live metadata."""
    metadata = snapshot.read_metadata(snapshot.STAGING_METADATA_PATH)
    if not metadata:
        raise SystemExit(f"No staging metadata at {snapshot.STAGING_METADATA_PATH}.")

    has_chroma = os.path.isdir(snapshot.STAGING_CHROMA_PATH)
    if has_chroma:
        rename_staging_collection(live_collection)

    metadata["corpus_path"] = f"{snapshot.SNAPSHOT_VECTORSTORE_PATH}/corpus.json"
    metadata["staging"] = False
    metadata["promoted_at"] = snapshot.ist_now().isoformat(timespec="seconds")
    if has_chroma and isinstance(metadata.get("chroma"), dict):
        metadata["chroma"].update({"path": snapshot.SNAPSHOT_CHROMA_PATH, "collection": live_collection})
    snapshot.write_json_atomic(os.path.join(snapshot.STAGING_VECTORSTORE_PATH, "metadata.json"), metadata)

    # Chroma first: it is the move most likely to fail (Windows file locks), and if it does,
    # nothing live has changed yet. metadata.json goes last because it triggers the app reload.
    if has_chroma:
        snapshot.replace_dir(snapshot.STAGING_CHROMA_PATH, snapshot.SNAPSHOT_CHROMA_PATH)
    snapshot.replace_dir(snapshot.STAGING_VECTORSTORE_PATH, snapshot.SNAPSHOT_VECTORSTORE_PATH)
    snapshot.write_json_atomic(snapshot.SNAPSHOT_METADATA_PATH, metadata)  # last: triggers app reload
    os.remove(snapshot.STAGING_METADATA_PATH)
    print(f"✅ Promoted staging → live (chroma: {'yes' if has_chroma else 'no'}).")
    return metadata


def publish(metadata: dict, remote: str, branch: str, push: bool) -> str:
    """Creates a parentless commit of the live snapshot files and force-pushes it to `branch`."""
    paths = [snapshot.SNAPSHOT_VECTORSTORE_PATH, snapshot.SNAPSHOT_METADATA_PATH]
    if os.path.isdir(snapshot.SNAPSHOT_CHROMA_PATH):
        paths.append(snapshot.SNAPSHOT_CHROMA_PATH)

    with tempfile.TemporaryDirectory() as tmp:
        env = {
            **os.environ,
            "GIT_INDEX_FILE": os.path.join(tmp, "snapshot.index"),
            "GIT_AUTHOR_NAME": os.getenv("GIT_AUTHOR_NAME", BOT_NAME),
            "GIT_AUTHOR_EMAIL": os.getenv("GIT_AUTHOR_EMAIL", BOT_EMAIL),
            "GIT_COMMITTER_NAME": os.getenv("GIT_COMMITTER_NAME", BOT_NAME),
            "GIT_COMMITTER_EMAIL": os.getenv("GIT_COMMITTER_EMAIL", BOT_EMAIL),
        }
        _git(["add", "--force", "--", *paths], env=env)  # -f: these paths are git-ignored on main
        tree = _git(["write-tree"], env=env)
        message = (
            f"data: refresh {metadata.get('scrape_date')} (run {metadata.get('run_id')})\n\n"
            f"generated_at: {metadata.get('generated_at')}\n"
            f"source commit: {metadata.get('git_sha')}\n"
            f"chunks: {metadata.get('total_chunks')} across {metadata.get('total_schemes')} schemes\n"
        )
        commit = _git(["commit-tree", tree, "-F", "-"], env=env, input_text=message)

    if push:
        _git(["push", "--force", remote, f"{commit}:refs/heads/{branch}"])
        print(f"✅ Force-pushed snapshot {commit[:12]} to {remote}/{branch}.")
    else:
        print(f"ℹ️ Built snapshot commit {commit[:12]} (not pushed: --no-push).")
    return commit


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--branch", default=snapshot.SNAPSHOT_BRANCH)
    p.add_argument("--remote", default="origin")
    p.add_argument("--no-push", action="store_true", help="promote and build the commit, but do not push")
    p.add_argument("--marker", default=snapshot.VALIDATION_MARKER_PATH)
    p.add_argument("--summary", default="")
    args = p.parse_args(argv)

    staged = snapshot.read_metadata(snapshot.STAGING_METADATA_PATH)
    if not staged:
        raise SystemExit(f"No staging build found ({snapshot.STAGING_METADATA_PATH}). Run ingest.py --staging.")
    check_marker(args.marker, staged)
    check_layout()

    metadata = promote(settings.vectorstore_collection)
    commit = publish(metadata, args.remote, args.branch, push=not args.no_push)
    if os.path.exists(args.marker):
        os.remove(args.marker)

    snapshot.append_summary(args.summary, "\n".join([
        "## 📦 Snapshot published",
        f"- Branch `{args.branch}` → `{commit[:12]}`{'' if not args.no_push else ' (not pushed)'}",
        f"- Scrape date **{metadata.get('scrape_date')}**, run `{metadata.get('run_id')}`, "
        f"{metadata.get('total_chunks')} chunks",
        f"- App hosts pick it up with `python scripts/sync_data.py` (no restart needed).",
    ]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
