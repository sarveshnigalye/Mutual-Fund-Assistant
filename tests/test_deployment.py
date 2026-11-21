"""Railway deployment changes (Docs/deployment-plan.md, Phase D1). No network: GitHub is faked."""

import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import limits
from app.config import settings
from app.ingestion import snapshot, sync

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_script(name):
    spec = importlib.util.spec_from_file_location(f"script_{name}", os.path.join(ROOT, "scripts", f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------------------
# Fake GitHub
# ------------------------------------------------------------------------------
def snapshot_tarball(generated_at, top="owner-repo-abc123", extra_member=None) -> bytes:
    """A gzip tarball shaped like GitHub's /tarball/<branch> response."""
    files = {
        f"{top}/data/metadata.json": json.dumps({"generated_at": generated_at, "scrape_date": "2026-11-21",
                                                 "total_chunks": 2, "run_id": "9"}),
        f"{top}/data/vectorstore/corpus.json": "[]",
    }
    if extra_member:
        files[extra_member] = "x"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, text in files.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_github(monkeypatch):
    """Serves metadata.json + tarball for repo 'owner/repo'; records requests."""
    state = {"generated_at": "g2", "calls": [], "status": 200, "extra_member": None}

    def urlopen(request, timeout=None):
        url = request.full_url
        state["calls"].append((url, request.headers.get("Authorization")))
        if state["status"] != 200:
            raise sync.urllib.error.HTTPError(url, state["status"], "nope", {}, None)
        if "/contents/" in url:
            return FakeResponse(json.dumps({"generated_at": state["generated_at"]}).encode())
        if "/tarball/" in url:
            return FakeResponse(snapshot_tarball(state["generated_at"], extra_member=state["extra_member"]))
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(sync.urllib.request, "urlopen", urlopen)
    return state


@pytest.fixture
def app_host(tmp_path, monkeypatch):
    """A host whose live data lives under tmp_path/data (like Railway's /data volume)."""
    root = tmp_path / "volume"
    monkeypatch.setattr(settings, "vectorstore_path", str(root / "vectorstore"))
    monkeypatch.setattr(settings, "chroma_db_path", str(root / "chroma"))
    monkeypatch.setattr(settings, "data_metadata_path", str(root / "metadata.json"))
    root.mkdir()
    return root


# ------------------------------------------------------------------------------
# D1.1 live paths follow settings
# ------------------------------------------------------------------------------
def test_live_paths_follow_settings(app_host):
    assert snapshot.live_vectorstore_path() == os.path.normpath(str(app_host / "vectorstore"))
    assert snapshot.live_metadata_path() == os.path.normpath(str(app_host / "metadata.json"))
    assert snapshot.live_data_root() == os.path.abspath(str(app_host))


def test_publish_refuses_non_repo_layout(app_host):
    publish = load_script("publish_snapshot")
    with pytest.raises(SystemExit, match="default data paths"):
        publish.check_layout()


# ------------------------------------------------------------------------------
# D1.2 GitHub sync
# ------------------------------------------------------------------------------
def test_sync_from_github_installs_into_volume(app_host, fake_github):
    result = sync.sync_from_github("owner/repo", "data-snapshot", token="t0k")
    assert result.status == "installed", result.message
    assert result.current == "g2" and result.total_chunks == 2
    assert snapshot.read_metadata(str(app_host / "metadata.json"))["generated_at"] == "g2"
    assert os.listdir(app_host / "vectorstore") == ["corpus.json"]
    assert not [d for d in os.listdir(app_host) if d.startswith(".sync-")]  # temp dir on the volume, cleaned
    assert all(auth == "Bearer t0k" for _, auth in fake_github["calls"])
    assert sync.last_result()["status"] == "installed"


def test_sync_from_github_skips_download_when_current(app_host, fake_github):
    assert sync.sync_from_github("owner/repo").status == "installed"
    calls = len(fake_github["calls"])
    result = sync.sync_from_github("owner/repo")
    assert result.status == "up_to_date"
    assert len(fake_github["calls"]) == calls + 1  # only the small metadata request
    assert "/contents/" in fake_github["calls"][-1][0]


def test_sync_from_github_failure_leaves_live_data(app_host, fake_github):
    (app_host / "vectorstore").mkdir()
    (app_host / "vectorstore" / "old.txt").write_text("old")
    fake_github["status"] = 404
    result = sync.sync_from_github("owner/private-repo")
    assert result.status == "failed"
    assert "SNAPSHOT_TOKEN" in result.message  # hint for private repos without a token
    assert os.listdir(app_host / "vectorstore") == ["old.txt"]


def test_sync_rejects_unsafe_archive(app_host, fake_github):
    fake_github["extra_member"] = "../escape.txt"
    result = sync.sync_from_github("owner/repo", force=True)
    assert result.status == "failed" and "unsafe path" in result.message
    assert not (app_host.parent / "escape.txt").exists()


def test_sync_without_repo_is_a_clean_failure(app_host):
    assert sync.sync_from_github("").status == "failed"


def test_sync_data_cli_from_github(app_host, fake_github, monkeypatch, capsys):
    monkeypatch.setattr(settings, "snapshot_repo", "owner/repo")
    sync_data = load_script("sync_data")
    assert sync_data.main(["--from-github"]) == 0
    assert "Installed snapshot g2" in capsys.readouterr().out


# ------------------------------------------------------------------------------
# D1.4 admin endpoints, D1.9 health
# ------------------------------------------------------------------------------
@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


def test_admin_endpoints_hidden_without_token(client, monkeypatch):
    monkeypatch.setattr(settings, "refresh_token", "")
    assert client.post("/api/admin/refresh-data").status_code == 404
    assert client.get("/api/admin/data-status").status_code == 404


def test_admin_endpoints_require_bearer_token(client, monkeypatch):
    monkeypatch.setattr(settings, "refresh_token", "s3cret")
    assert client.post("/api/admin/refresh-data").status_code == 401
    assert client.post("/api/admin/refresh-data", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/api/admin/refresh-data", headers={"Authorization": "Basic s3cret"}).status_code == 401


def test_refresh_starts_background_sync(client, monkeypatch):
    monkeypatch.setattr(settings, "refresh_token", "s3cret")
    monkeypatch.setattr(settings, "snapshot_repo", "owner/repo")
    called = threading.Event()
    monkeypatch.setattr(sync, "sync_configured", lambda force=False: called.set())

    resp = client.post("/api/admin/refresh-data", headers={"Authorization": "Bearer s3cret"})
    assert resp.status_code == 202 and resp.json()["status"] == "started"
    assert called.wait(5)


def test_refresh_without_repo_is_409(client, monkeypatch):
    monkeypatch.setattr(settings, "refresh_token", "s3cret")
    monkeypatch.setattr(settings, "snapshot_repo", "")
    assert client.post("/api/admin/refresh-data", headers={"Authorization": "Bearer s3cret"}).status_code == 409


def test_data_status(client, monkeypatch):
    monkeypatch.setattr(settings, "refresh_token", "s3cret")
    body = client.get("/api/admin/data-status", headers={"Authorization": "Bearer s3cret"}).json()
    assert {"live", "loaded_snapshot", "index_loaded", "sync_running", "last_sync", "library_mismatches"} <= set(body)


def test_health_reports_index_state(client):
    body = client.get("/api/health").json()
    assert body["status"] == "healthy"
    assert {"index_loaded", "snapshot_generated_at", "scrape_date"} <= set(body)


# ------------------------------------------------------------------------------
# D1.8 rate limit + body size
# ------------------------------------------------------------------------------
@pytest.fixture
def limited_client(monkeypatch):
    monkeypatch.setattr(limits, "limiter", limits.SlidingWindowLimiter())
    app = FastAPI()
    app.add_middleware(limits.RequestLimitsMiddleware)

    @app.post("/api/chat")
    def chat():
        return {"ok": True}

    @app.get("/api/threads")
    def threads():
        return []

    return TestClient(app)


def test_rate_limit_per_ip(limited_client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 2)
    a = {"X-Forwarded-For": "1.1.1.1, 10.0.0.1"}
    assert [limited_client.post("/api/chat", json={}, headers=a).status_code for _ in range(3)] == [200, 200, 429]
    blocked = limited_client.post("/api/chat", json={}, headers=a)
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) >= 1
    assert limited_client.post("/api/chat", json={}, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200
    assert limited_client.get("/api/threads", headers=a).status_code == 200  # only /api/chat is limited


def test_rate_limit_off_by_default(limited_client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 0)
    assert all(limited_client.post("/api/chat", json={}).status_code == 200 for _ in range(30))


def test_request_too_large(limited_client, monkeypatch):
    monkeypatch.setattr(settings, "max_request_bytes", 100)
    assert limited_client.post("/api/chat", content=b"x" * 101,
                               headers={"Content-Type": "application/json"}).status_code == 413


def test_sliding_window_recovers():
    lim = limits.SlidingWindowLimiter()
    assert lim.allow("ip", 1, now=0.0) == 0
    assert lim.allow("ip", 1, now=30.0) == pytest.approx(30.0)
    assert lim.allow("ip", 1, now=60.0) == 0


# ------------------------------------------------------------------------------
# D1.3 launcher, D1.6 Selenium-free runtime, D1.7 library versions
# ------------------------------------------------------------------------------
def test_launcher_port_and_host(monkeypatch):
    start = load_script("railway_start")
    monkeypatch.setenv("PORT", "4321")
    monkeypatch.delenv("HOST", raising=False)
    assert start.port() == 4321
    assert start.host() == ("0.0.0.0" if os.name == "nt" else "::")  # dual-stack on Linux (Railway)
    monkeypatch.setenv("HOST", "127.0.0.1")
    assert start.host() == "127.0.0.1"
    monkeypatch.delenv("PORT")
    assert start.port() == 8000


def test_launcher_startup_sync_is_never_fatal(monkeypatch):
    start = load_script("railway_start")
    monkeypatch.setattr(settings, "snapshot_repo", "owner/repo")

    def boom(force=False):
        raise RuntimeError("github down")

    monkeypatch.setattr(sync, "sync_configured", boom)
    start.startup_sync()  # must not raise


def test_app_imports_without_selenium():
    code = "import sys; sys.modules['selenium'] = None; import app.main; print('ok')"
    proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0 and "ok" in proc.stdout, proc.stderr[-2000:]


def test_library_mismatch_detection():
    installed = snapshot.library_versions()
    assert "scikit-learn" in installed
    assert snapshot.library_mismatches({"library_versions": dict(installed)}) == {}
    mismatch = snapshot.library_mismatches({"library_versions": {"scikit-learn": "0.0.1"}})
    assert mismatch == {"scikit-learn": ("0.0.1", installed["scikit-learn"])}
    assert snapshot.library_mismatches(None) == {}
