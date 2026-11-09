"""Regression checks for both supported Streamlit entrypoints.

No backend or API keys are required; only the UI import/startup path is tested.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("entrypoint", ["streamlit_app.py", "ui/app.py"])
def test_streamlit_starts_without_pythonpath(entrypoint, monkeypatch):
    # Streamlit's script runner normally runs the UI script from its directory.
    # Prior releases failed at "from ui import ..." for ui/app.py.
    monkeypatch.delenv("PYTHONPATH", raising=False)
    app = AppTest.from_file(str(ROOT / entrypoint), default_timeout=20).run()
    assert not app.exception, [str(error.message) for error in app.exception]
