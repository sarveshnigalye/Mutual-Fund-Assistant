"""Launcher for Streamlit frontend UI."""

import os
import subprocess
import sys

def main():
    frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "streamlit_app.py"))
    python_exe = sys.executable
    cmd = [python_exe, "-m", "streamlit", "run", frontend_path, "--server.port", "8501"]
    print(f"🌐 Launching Streamlit frontend on http://localhost:8501...")
    subprocess.run(cmd)

if __name__ == "__main__":
    main()

