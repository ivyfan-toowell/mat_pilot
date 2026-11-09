"""异步长任务的提交回执与状态模型。"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

JobKind = Literal["agent_run", "document_index", "experiment_extract", "structured_experiment_extract"]
JobStatus = Literal["queued", "running", "succeeded", "failed"]


class JobAccepted(BaseModel):
    job_id: UUID
    kind: JobKind
    status: Literal["queued"] = "queued"


class JobRecord(BaseModel):
    job_id: UUID
    tenant_id: str
    kind: JobKind
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    request: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: dict[str, str] | None = None


class IndexJobRequest(BaseModel):
    document_id: UUID


class ExtractJobRequest(BaseModel):
    document_id: UUID
