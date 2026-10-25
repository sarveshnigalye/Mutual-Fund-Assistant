"""Unified launcher to run both FastAPI backend and Streamlit frontend concurrently."""

import os
import subprocess
import sys
import time
import requests


def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    python_exe = sys.executable
    server_script = os.path.join(root_dir, "scripts", "run_server.py")
    ui_script = os.path.join(root_dir, "scripts", "run_ui.py")

    print("=================================================================")
    print("🚀 Starting HDFC Mutual Fund Facts-Only Assistant (Full Stack)")
    print("=================================================================")

    # 1. Start FastAPI backend
    print("1️⃣  Starting FastAPI backend on http://127.0.0.1:8000...")
    backend_proc = subprocess.Popen([python_exe, server_script])

    # Wait for backend to be ready
    health_url = "http://127.0.0.1:8000/api/health"
    ready = False
    for _ in range(15):
        time.sleep(1)
        try:
            r = requests.get(health_url, timeout=1)
            if r.status_code == 200:
                print("   ✅ Backend health check passed!")
                ready = True
                break
        except Exception:
            pass

    if not ready:
        print("   ⚠️ Backend health check timed out, proceeding to start frontend...")

    # 2. Start Streamlit frontend
    print("2️⃣  Starting Streamlit frontend on http://localhost:8501...")
    frontend_proc = subprocess.Popen([python_exe, ui_script])

    print("\n🎉 Both services are running:")
    print("   👉 Streamlit Frontend:   http://localhost:8501")
    print("   👉 FastAPI API Docs:     http://127.0.0.1:8000/docs")
    print("   👉 FastAPI Health Check: http://127.0.0.1:8000/health")
    print("\nPress Ctrl+C to terminate both servers.\n")

    try:
        while True:
            time.sleep(1)
            if backend_proc.poll() is not None:
                print("Backend terminated unexpectedly.")
                break
            if frontend_proc.poll() is not None:
                print("Frontend terminated.")
                break
    except KeyboardInterrupt:
        print("\n🛑 Shutting down services...")
    finally:
        if backend_proc.poll() is None:
            backend_proc.terminate()
        if frontend_proc.poll() is None:
            frontend_proc.terminate()
        print("Shutdown complete.")


if __name__ == "__main__":
    main()
