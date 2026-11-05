"""提供科研助手任务执行、历史结果与协作阶段记录查询接口。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.agents.collaboration import CollaborativeAgent, route_workflow
from app.agents.research import ResearchAgent
from app.core.auth import PrincipalDep
from app.core.config import Settings, get_settings, tenant_data_dir
from app.schemas.agent import AgentCheckpoint, AgentRequest, AgentResult, AgentRunSummary
from app.services.catalog_service import list_agent_runs, load_agent_checkpoint, load_agent_run

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/runs", response_model=list[AgentRunSummary])
def run_catalog(
    settings: SettingsDep,
    principal: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[AgentRunSummary]:
    return list_agent_runs(tenant_data_dir(settings, principal.tenant_id), limit)


@router.post("/run", response_model=AgentResult)
def run(
    request: AgentRequest, settings: SettingsDep, principal: PrincipalDep
) -> AgentResult:
    mode, reason = route_workflow(request)
    if mode == "collaborative":
        return CollaborativeAgent(settings, principal.tenant_id).run(request, reason)
    return ResearchAgent(settings, principal.tenant_id).run(request, routing_reason=reason)


@router.get("/runs/{run_id}/checkpoint", response_model=AgentCheckpoint)
def checkpoint(
    run_id: UUID, settings: SettingsDep, principal: PrincipalDep
) -> AgentCheckpoint:
    return AgentCheckpoint.model_validate(
        load_agent_checkpoint(tenant_data_dir(settings, principal.tenant_id), run_id)
    )


@router.get("/runs/{run_id}", response_model=AgentResult)
def get_run(run_id: UUID, settings: SettingsDep, principal: PrincipalDep) -> AgentResult:
    return load_agent_run(tenant_data_dir(settings, principal.tenant_id), run_id)
