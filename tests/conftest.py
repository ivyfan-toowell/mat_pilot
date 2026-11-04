"""Isolated project-scoped test data, removed after each test."""

import shutil
from pathlib import Path
from uuid import uuid4

import pytest


@pytest.fixture
def workspace_dir():
    root = Path(__file__).resolve().parents[1] / ".pytest-work"
    root.mkdir(exist_ok=True)
    directory = root / str(uuid4())
    directory.mkdir()  # Default mode preserves workspace ACL inheritance on Windows.
    try:
        yield directory
    finally:
        resolved = directory.resolve()
        if resolved.parent != root.resolve():
            raise RuntimeError("test directory escaped the expected workspace")
        shutil.rmtree(resolved)
