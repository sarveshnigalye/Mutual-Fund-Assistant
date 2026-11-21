"""GitHub issue alerting for the daily data refresh (Phase 7.10). Uses the `gh` CLI.

    # on failure: open an issue labelled data-refresh-failure, or comment on the open one
    STEPS_JSON='${{ toJSON(steps) }}' python scripts/report_failure.py --run-url URL
    # on success: close any open data-refresh-failure issue
    python scripts/report_failure.py --resolve --run-url URL

Never fails the job itself: an alerting problem is printed, and the exit code is 0.
Standard library only, so it still works when the failing step was `pip install`.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
IST = timezone(timedelta(hours=5, minutes=30))
# Same paths as app/ingestion/snapshot.py (not imported: it needs the project's dependencies)
STAGING_METADATA_PATH = os.path.join(ROOT, "data", "metadata_staging.json")
VALIDATION_MARKER_PATH = os.path.join(ROOT, "data", "validation_staging.json")

LABEL = "data-refresh-failure"
TITLE = "Daily data refresh failed"

# Workflow step ids in pipeline order, with the name shown in the alert.
STAGES = [
    ("setup", "Set up Python / install dependencies"),
    ("ingest", "Scrape → normalize → clean → chunk → embed → store (staging)"),
    ("validate", "Validation gate"),
    ("publish", "Promote staging and publish snapshot"),
    ("notify", "Notify the deployed app (Railway) to load the snapshot"),
]


def _gh(args, input_text=None) -> str:
    proc = subprocess.run(["gh", *args], cwd=ROOT, input=input_text, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def failing_stage(steps_json: str) -> str:
    try:
        steps = json.loads(steps_json or "{}")
    except ValueError:
        steps = {}
    for step_id, name in STAGES:
        if steps.get(step_id, {}).get("outcome") == "failure":
            return name
    return "Unknown step (see the run log)"


def failure_details() -> list:
    lines = []
    meta = _read_json(STAGING_METADATA_PATH)
    for f in meta.get("failures") or []:
        lines.append(f"- `{f.get('scheme_id')}` failed at **{f.get('stage')}**: {f.get('error')}")
    marker = _read_json(VALIDATION_MARKER_PATH)
    for e in marker.get("errors") or []:
        lines.append(f"- {e}")
    return lines


def open_issues() -> list:
    out = _gh(["issue", "list", "--label", LABEL, "--state", "open", "--json", "number", "--limit", "20"])
    return [i["number"] for i in json.loads(out or "[]")]


def report(run_url: str, steps_json: str) -> None:
    stage = failing_stage(steps_json)
    details = failure_details()
    body = "\n".join([
        f"**Failed stage:** {stage}",
        f"**Run:** {run_url}",
        f"**When:** {datetime.now(IST).strftime('%Y-%m-%d %H:%M')} IST",
        "",
        "The previous snapshot is still live; users keep getting answers from it.",
        *(["", "**Details**", *details] if details else []),
    ])
    _gh(["label", "create", LABEL, "--color", "B60205", "--force",
         "--description", "Scheduled data refresh failed; previous snapshot still live"])
    existing = open_issues()
    if existing:
        _gh(["issue", "comment", str(existing[0]), "--body-file", "-"], input_text=body)
        print(f"Commented on issue #{existing[0]} ({stage}).")
    else:
        url = _gh(["issue", "create", "--title", TITLE, "--label", LABEL, "--body-file", "-"], input_text=body)
        print(f"Opened {url} ({stage}).")


def resolve(run_url: str) -> None:
    for number in open_issues():
        _gh(["issue", "close", str(number), "--comment", f"Resolved: refresh succeeded in {run_url}"])
        print(f"Closed issue #{number}.")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run-url", required=True)
    p.add_argument("--resolve", action="store_true", help="close open failure issues (successful run)")
    args = p.parse_args(argv)
    try:
        if args.resolve:
            resolve(args.run_url)
        else:
            report(args.run_url, os.getenv("STEPS_JSON", ""))
    except Exception as e:  # alerting must never mask the real failure
        print(f"::warning::Could not update the {LABEL} issue: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
