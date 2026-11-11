"""Transient Windows file locks must not destroy or truncate saved job state."""

import errno
from pathlib import Path

import pytest

from app.core.errors import ServiceError
from app.core.io import atomic_write_text


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_atomic_replace_retries_transient_windows_lock(workspace_dir, monkeypatch, winerror):
    path = workspace_dir / "state.json"
    path.write_text("old", encoding="utf-8")
    original_replace = Path.replace
    attempts = []
    sleeps = []

    def replace(source, destination):
        attempts.append(source)
        assert destination.read_text(encoding="utf-8") == "old"
        if len(attempts) <= 2:
            error = PermissionError("temporary Windows file lock")
            error.winerror = winerror
            raise error
        return original_replace(source, destination)

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr("app.core.io.time.sleep", sleeps.append)
    atomic_write_text(path, "new")
    assert path.read_text(encoding="utf-8") == "new"
    assert len(attempts) == 3 and sleeps == [0.01, 0.02]
    assert not list(workspace_dir.glob("*.tmp"))


@pytest.mark.parametrize("winerror,expected_attempts", [(5, 5), (None, 1)])
def test_persistent_denial_keeps_original_and_cleans_temp(
    workspace_dir, monkeypatch, winerror, expected_attempts
):
    path = workspace_dir / "state.json"
    path.write_text("old", encoding="utf-8")
    error = PermissionError("fixture denied")
    error.winerror = winerror
    attempts = []
    sleeps = []

    def replace(source, destination):
        attempts.append(source)
        raise error

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr("app.core.io.time.sleep", sleeps.append)
    with pytest.raises(ServiceError) as caught:
        atomic_write_text(path, "new", error_message="fixture storage unavailable")
    assert caught.value.code == "storage_unavailable" and caught.value.__cause__ is error
    assert len(attempts) == expected_attempts
    assert len(sleeps) == expected_attempts - 1
    assert path.read_text(encoding="utf-8") == "old"
    assert not list(workspace_dir.glob("*.tmp"))


def test_non_lock_error_is_not_retried(workspace_dir, monkeypatch):
    path = workspace_dir / "state.json"
    path.write_text("old", encoding="utf-8")
    error = OSError(errno.ENOSPC, "fixture disk full")
    sleeps = []

    def replace(source, destination):
        raise error

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr("app.core.io.time.sleep", sleeps.append)
    with pytest.raises(ServiceError) as caught:
        atomic_write_text(path, "new")
    assert caught.value.__cause__ is error and not sleeps
    assert path.read_text(encoding="utf-8") == "old"
    assert not list(workspace_dir.glob("*.tmp"))
