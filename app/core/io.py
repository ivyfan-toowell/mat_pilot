"""共享原子写，避免崩溃留下半截 JSON。"""

from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

from app.core.errors import ServiceError


def atomic_write_text(path: Path, text: str, *, error_message: str = "状态保存失败。") -> None:
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(text, encoding="utf-8")
        for attempt in range(5):
            try:
                temporary.replace(path)
                break
            except PermissionError as exc:
                # Windows readers/virus scanners can briefly deny replacement.
                # Never fall back to truncating the original or retry indefinitely.
                if getattr(exc, "winerror", None) not in {5, 32, 33} or attempt == 4:
                    raise
                time.sleep(0.01 * 2**attempt)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ServiceError("storage_unavailable", error_message, 503) from exc
