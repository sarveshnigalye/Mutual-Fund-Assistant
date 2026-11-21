"""Pull the latest published snapshot onto this app host (Phase 7.9).

    python scripts/sync_data.py                              # git: fetch origin/data-snapshot (repo checkout)
    python scripts/sync_data.py --from-github owner/repo     # HTTPS download (no .git needed, e.g. Railway)
    python scripts/sync_data.py --from-github                # …using SNAPSHOT_REPO / SNAPSHOT_TOKEN from env
    python scripts/sync_data.py --from-dir ./artifact        # an unzipped workflow artifact
    python scripts/sync_data.py --force                      # reinstall even if already current

Data goes to this host's live paths (VECTORSTORE_PATH, CHROMA_DB_PATH, DATA_METADATA_PATH):
the ChromaDB and vectorstore directories are replaced by renames from a temp dir on the same
disk, and metadata.json is written last. A running backend notices the new `generated_at`
within INDEX_RELOAD_CHECK_SECONDS (default 60 s) and reloads — no restart.

Exit code: 0 when installed or already up to date, 1 when the sync failed (live data unchanged).
"""

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
if __name__ == "__main__":
    os.chdir(ROOT)

from app.config import settings
from app.ingestion import snapshot, sync


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = p.add_mutually_exclusive_group()
    source.add_argument("--from-dir", help="directory that contains data/ (e.g. an unzipped artifact)")
    source.add_argument("--from-github", nargs="?", const="", metavar="OWNER/REPO",
                        help="download over HTTPS (default repo: $SNAPSHOT_REPO; token: $SNAPSHOT_TOKEN)")
    p.add_argument("--remote", default="origin", help="git remote (git mode)")
    p.add_argument("--branch", default=None, help=f"snapshot branch (default: {snapshot.SNAPSHOT_BRANCH})")
    p.add_argument("--force", action="store_true", help="install even if the snapshot is already current")
    args = p.parse_args(argv)
    branch = args.branch or settings.snapshot_branch or snapshot.SNAPSHOT_BRANCH

    if args.from_dir:
        result = sync.sync_from_dir(args.from_dir, force=args.force)
    elif args.from_github is not None:
        repo = args.from_github or settings.snapshot_repo
        result = sync.sync_from_github(repo, branch, settings.snapshot_token or None, force=args.force)
    else:
        result = sync.sync_from_git(args.remote, branch, force=args.force, cwd=ROOT)

    if result.status == "failed":
        raise SystemExit(f"❌ {result.message}")
    if result.status == "up_to_date":
        print(f"Already up to date: snapshot {result.current} (scrape date {result.scrape_date}).")
    else:
        print(f"✅ Installed snapshot {result.current} — scrape date {result.scrape_date}, "
              f"{result.total_chunks} chunks. (previous: {result.previous or 'none'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
