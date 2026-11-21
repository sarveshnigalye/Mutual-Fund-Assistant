"""Smoke test for Streamlit frontend app."""

import os
from streamlit.testing.v1 import AppTest


def test_streamlit_app_loads_and_renders():
    app_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "streamlit_app.py"))
    at = AppTest.from_file(app_path, default_timeout=35.0)
    at.run(timeout=35.0)

    # Must run without unhandled exceptions
    assert len(at.exception) == 0, f"AppTest raised exceptions: {[e.value for e in at.exception]}"

    # Verify key UI components exist
    assert len(at.button) > 0, "No buttons rendered in Streamlit app"
    assert len(at.markdown) > 0, "No markdown blocks rendered in Streamlit app"

    # Disclaimer must always be visible, and the sidebar must offer "New Chat"
    assert any("Facts-only. No investment advice." in m.value for m in at.markdown)
    assert any("New Chat" in b.label for b in at.button)

