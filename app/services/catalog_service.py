"""汇总已解析文献与已完成科研任务，供界面按名称选择和回读本地记录。"""

import logging
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from app.schemas.agent import AgentResult, AgentRunSummary
from app.schemas.document import DocumentSummary, ParsedDocument

logger = logging.getLogger(__name__)


def _paths(folder: Path, pattern: str) -> list[Path]:
    if not folder.exists():
        return []
    candidates = []
    for path in folder.glob(pattern):
        if path.is_symlink() or path.parent.is_symlink():
            continue
        identifier = path.parent.name if path.name == "parsed.json" else path.stem
        try:
            UUID(identifier)
            candidates.append((path.stat().st_mtime_ns, path))
        except (ValueError, OSError):
            continue
    return [path for _, path in sorted(candidates, reverse=True)[:500]]


def list_documents(data_dir: Path, limit: int = 100) -> list[DocumentSummary]:
    records = []
    for path in _paths(data_dir / "documents", "*/parsed.json"):
        try:
            document = ParsedDocument.model_validate_json(path.read_text(encoding="utf-8"))
            if str(document.document_id) != path.parent.name:
                continue
            records.append(
                DocumentSummary(
                    **document.model_dump(),
                    has_experiments=(path.parent / "experiments.json").is_file(),
                )
            )
        except (OSError, ValidationError):
            logger.warning("跳过不可读取的文献归档：%s", path.parent.name)
    return sorted(records, key=lambda item: item.parsed_at, reverse=True)[:limit]


def list_agent_runs(data_dir: Path, limit: int = 50) -> list[AgentRunSummary]:
    records = []
    for path in _paths(data_dir / "agent_runs", "*.json"):
        try:
            result = AgentResult.model_validate_json(path.read_text(encoding="utf-8"))
            if str(result.run_id) != path.stem:
                continue
            records.append(AgentRunSummary.model_validate(result.model_dump()))
        except (OSError, ValidationError):
            logger.warning("跳过不可读取的任务归档：%s", path.stem)
    return sorted(records, key=lambda item: item.created_at, reverse=True)[:limit]
