"""Canonical Streamlit entrypoint.

Execute the UI page as a script inside Streamlit's current ScriptRunContext.
Avoid importing a module whose top-level Streamlit calls can be cached across
reruns or executed outside the active script context.
"""

import runpy
from pathlib import Path

_UI_SCRIPT = Path(__file__).resolve().parent / "ui" / "app.py"
runpy.run_path(str(_UI_SCRIPT), run_name="__main__")
