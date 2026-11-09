"""异步长任务提交与状态查询。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.core.auth import Principal, PrincipalDep
from app.core.config import Settings, get_settings, tenant_data_dir
from app.schemas.agent import AgentRequest
from app.schemas.job import (
    ExtractJobRequest,
    IndexJobRequest,
    JobAccepted,
    JobKind,
    JobRecord,
)
from app.services.job_service import JobStore, get_worker

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _accept(
    response: Response,
    settings: Settings,
    principal: Principal,
    kind: JobKind,
    request: dict,
) -> JobAccepted:
    job = get_worker().submit(settings, principal.tenant_id, kind, request)
    response.status_code = status.HTTP_202_ACCEPTED
    return JobAccepted(job_id=job.job_id, kind=job.kind, status="queued")


@router.post("/agent", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
def enqueue_agent(
    body: AgentRequest,
    response: Response,
    settings: SettingsDep,
    principal: PrincipalDep,
) -> JobAccepted:
    return _accept(response, settings, principal, "agent_run", body.model_dump(mode="json"))


@router.post(
    "/knowledge/index", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED
)
def enqueue_index(
    body: IndexJobRequest,
    response: Response,
    settings: SettingsDep,
    principal: PrincipalDep,
) -> JobAccepted:
    return _accept(response, settings, principal, "document_index", body.model_dump(mode="json"))


@router.post(
    "/documents/extract", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED
)
def enqueue_extract(
    body: ExtractJobRequest,
    response: Response,
    settings: SettingsDep,
    principal: PrincipalDep,
) -> JobAccepted:
    return _accept(
        response, settings, principal, "experiment_extract", body.model_dump(mode="json")
    )


@router.post(
    "/experimental-knowledge/extract",
    response_model=JobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_structured_extract(
    body: ExtractJobRequest,
    response: Response,
    settings: SettingsDep,
    principal: PrincipalDep,
) -> JobAccepted:
    return _accept(
        response, settings, principal,
        "structured_experiment_extract", body.model_dump(mode="json")
    )


@router.get("/{job_id}", response_model=JobRecord)
def get_job(job_id: UUID, settings: SettingsDep, principal: PrincipalDep) -> JobRecord:
    return JobStore(tenant_data_dir(settings, principal.tenant_id)).load(job_id)
