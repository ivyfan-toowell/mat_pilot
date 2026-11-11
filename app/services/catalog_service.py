"""汇总已解析文献与已完成科研任务，供界面按名称选择和回读本地记录。"""

import json
import logging
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from app.core.config import LOCAL_TENANT_ID, Settings
from app.core.errors import ServiceError
from app.schemas.agent import AgentResult, AgentRunSummary
from app.schemas.document import DocumentCatalogPage, DocumentSummary, ParsedDocument
from app.services.document_store import DocumentStore

logger = logging.getLogger(__name__)


def _paths(folder: Path, pattern: str, maximum: int | None = 500) -> list[Path]:
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
    return [path for _, path in sorted(candidates, reverse=True)[:maximum]]


def list_documents(
    data_dir: Path,
    limit: int = 100,
    settings: Settings | None = None,
    tenant_id: str = LOCAL_TENANT_ID,
) -> list[DocumentSummary]:
    return document_page(data_dir, limit, settings, tenant_id).items


def document_page(
    data_dir: Path,
    limit: int = 10,
    settings: Settings | None = None,
    tenant_id: str = LOCAL_TENANT_ID,
    *,
    offset: int = 0,
    query: str = "",
    deleted: bool = False,
) -> DocumentCatalogPage:
    if settings is not None and settings.database_url:
        return DocumentStore(settings, tenant_id).page(
            limit=limit, offset=offset, query=query, deleted=deleted
        )
    records = []
    for path in _paths(data_dir / "documents", "*/parsed.json", maximum=None):
        try:
            document = ParsedDocument.model_validate_json(path.read_text(encoding="utf-8"))
            if str(document.document_id) != path.parent.name:
                continue
            if bool(document.deleted_at) != deleted:
                continue
            searchable = " ".join([document.title, document.filename, *document.authors])
            if query.casefold() not in searchable.casefold():
                continue
            records.append(
                DocumentSummary(
                    **document.model_dump(),
                    has_experiments=(path.parent / "experiments.json").is_file(),
                )
            )
        except (OSError, ValidationError):
            logger.warning("跳过不可读取的文献归档：%s", path.parent.name)
    records.sort(key=lambda item: (item.parsed_at, str(item.document_id)), reverse=True)
    return DocumentCatalogPage(
        items=records[offset : offset + limit], total=len(records), limit=limit, offset=offset
    )


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


def load_agent_run(data_dir: Path, run_id: UUID) -> AgentResult:
    try:
        return AgentResult.model_validate_json(
            (data_dir / "agent_runs" / f"{run_id}.json").read_text(encoding="utf-8")
        )
    except FileNotFoundError as exc:
        raise ServiceError("run_not_found", "未找到该 Agent 任务。", 404) from exc


def load_agent_checkpoint(data_dir: Path, run_id: UUID) -> dict:
    try:
        return json.loads(
            (data_dir / "agent_runs" / f"{run_id}.checkpoint.json").read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        raise ServiceError("checkpoint_not_found", "未找到该协作任务的阶段状态。", 404) from None
