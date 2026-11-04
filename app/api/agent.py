"""提供科研助手任务执行、历史结果与协作阶段记录查询接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.agents.collaboration import CollaborativeAgent, route_workflow
from app.agents.research import ResearchAgent
from app.core.config import Settings, get_settings
from app.core.errors import ServiceError
from app.schemas.agent import AgentRequest, AgentResult, AgentRunSummary
from app.services.catalog_service import list_agent_runs

router = APIRouter(prefix="/api/agent", tags=["agent"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/runs", response_model=list[AgentRunSummary])
def run_catalog(
    settings: SettingsDep, limit: Annotated[int, Query(ge=1, le=100)] = 50
) -> list[AgentRunSummary]:
    return list_agent_runs(settings.data_dir, limit)


@router.post("/run", response_model=AgentResult)
def run(request: AgentRequest, settings: SettingsDep) -> AgentResult:
    mode, reason = route_workflow(request)
    if mode == "collaborative":
        return CollaborativeAgent(settings).run(request, reason)
    return ResearchAgent(settings).run(request, routing_reason=reason)


@router.get("/runs/{run_id}/checkpoint")
def checkpoint(run_id: UUID, settings: SettingsDep) -> dict:
    import json

    try:
        return json.loads(
            (settings.data_dir / "agent_runs" / f"{run_id}.checkpoint.json").read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError:
        raise ServiceError("checkpoint_not_found", "未找到该协作任务的阶段状态。", 404) from None


@router.get("/runs/{run_id}", response_model=AgentResult)
def get_run(run_id: UUID, settings: SettingsDep) -> AgentResult:
    try:
        return AgentResult.model_validate_json(
            (settings.data_dir / "agent_runs" / f"{run_id}.json").read_text(encoding="utf-8")
        )
    except FileNotFoundError as exc:
        raise ServiceError("run_not_found", "未找到该 Agent 任务。", 404) from exc
