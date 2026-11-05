"""共享原子写，避免崩溃留下半截 JSON。"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.core.errors import ServiceError


def atomic_write_text(path: Path, text: str, *, error_message: str = "状态保存失败。") -> None:
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ServiceError("storage_unavailable", error_message, 503) from exc
