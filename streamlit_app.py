"""Stable Streamlit entrypoint located at the repository root.

Start with:
    uv run --locked --all-extras streamlit run streamlit_app.py

This avoids reliance on a manually configured PYTHONPATH and delegates the
existing six-workspace UI to its single authoritative implementation.
"""

from ui import app  # noqa: F401
