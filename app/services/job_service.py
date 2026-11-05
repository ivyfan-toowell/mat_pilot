"""租户级异步任务持久化与进程内执行队列。"""

from __future__ import annotations

import logging
import queue
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.agents.collaboration import CollaborativeAgent, route_workflow
from app.agents.research import ResearchAgent
from app.core.config import Settings, tenant_data_dir
from app.core.errors import ServiceError
from app.core.io import atomic_write_text
from app.ingestion.extractor import ExperimentExtractor
from app.schemas.agent import AgentRequest
from app.schemas.job import JobKind, JobRecord
from app.services.document_service import DocumentService
from app.services.rag_service import RagService

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


class JobStore:
    def __init__(self, data_dir: Path) -> None:
        self.directory = data_dir / "jobs"

    def path(self, job_id: UUID) -> Path:
        return self.directory / f"{job_id}.json"

    def create(self, tenant_id: str, kind: JobKind, request: dict) -> JobRecord:
        job = JobRecord(
            job_id=uuid4(),
            tenant_id=tenant_id,
            kind=kind,
            status="queued",
            created_at=_now(),
            updated_at=_now(),
            request=request,
        )
        atomic_write_text(
            self.path(job.job_id),
            job.model_dump_json(indent=2),
            error_message="任务状态保存失败。",
        )
        return job

    def load(self, job_id: UUID) -> JobRecord:
        try:
            return JobRecord.model_validate_json(self.path(job_id).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ServiceError("job_not_found", "未找到该异步任务。", 404) from exc

    def save(self, job: JobRecord) -> JobRecord:
        job.updated_at = _now()
        atomic_write_text(
            self.path(job.job_id),
            job.model_dump_json(indent=2),
            error_message="任务状态保存失败。",
        )
        return job


def execute_job(settings: Settings, tenant_id: str, job: JobRecord) -> JobRecord:
    store = JobStore(tenant_data_dir(settings, tenant_id))
    job.status = "running"
    store.save(job)
    try:
        if job.kind == "agent_run":
            request = AgentRequest.model_validate(job.request)
            mode, reason = route_workflow(request)
            if mode == "collaborative":
                result = CollaborativeAgent(settings, tenant_id).run(request, reason)
            else:
                result = ResearchAgent(settings, tenant_id).run(request, routing_reason=reason)
            job.result = result.model_dump(mode="json")
        elif job.kind == "document_index":
            document_id = UUID(str(job.request["document_id"]))
            document = DocumentService(
                tenant_data_dir(settings, tenant_id), settings, tenant_id
            ).load(document_id)
            job.result = RagService(settings, tenant_id).index(document)
        elif job.kind == "experiment_extract":
            document_id = UUID(str(job.request["document_id"]))
            document = DocumentService(
                tenant_data_dir(settings, tenant_id), settings, tenant_id
            ).load(document_id)
            extraction = ExperimentExtractor(settings, tenant_id).extract(document)
            job.result = extraction.model_dump(mode="json")
        else:
            raise ServiceError("unknown_job_kind", "不支持的任务类型。", 422)
        job.status = "succeeded"
        job.error = None
    except ServiceError as exc:
        job.status = "failed"
        job.error = {"code": exc.code, "message": exc.message}
        job.result = None
    except Exception:
        logger.exception("async job failed job_id=%s kind=%s", job.job_id, job.kind)
        job.status = "failed"
        job.error = {"code": "job_failed", "message": "任务执行失败。"}
        job.result = None
    store.save(job)
    return job


class JobWorker:
    """In-process queue worker. Not a distributed queue; suitable for single-host MVP."""

    def __init__(self, workers: int = 2) -> None:
        self._queue: queue.Queue[tuple[Settings, str, UUID] | None] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._workers = max(1, workers)
        self._started = False

    def start(self, workers: int | None = None) -> None:
        if self._started:
            return
        if workers is not None:
            self._workers = max(1, workers)
        self._started = True
        for index in range(self._workers):
            thread = threading.Thread(
                target=self._loop, name=f"matpilot-job-{index}", daemon=True
            )
            thread.start()
            self._threads.append(thread)

    def stop(self, timeout: float = 5.0) -> None:
        if not self._started:
            return
        for _ in self._threads:
            self._queue.put(None)
        for thread in self._threads:
            thread.join(timeout=timeout)
        self._threads.clear()
        self._started = False

    def submit(self, settings: Settings, tenant_id: str, kind: JobKind, request: dict) -> JobRecord:
        if not self._started:
            raise ServiceError("job_worker_stopped", "异步任务执行器未启动。", 503)
        job = JobStore(tenant_data_dir(settings, tenant_id)).create(tenant_id, kind, request)
        self._queue.put((settings, tenant_id, job.job_id))
        return job

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                settings, tenant_id, job_id = item
                store = JobStore(tenant_data_dir(settings, tenant_id))
                job = store.load(job_id)
                try:
                    execute_job(settings, tenant_id, job)
                except Exception:
                    logger.exception("unhandled job failure job_id=%s", job_id)
                    job = store.load(job_id)
                    if job.status != "failed":
                        job.status = "failed"
                        job.error = {"code": "job_failed", "message": "任务执行失败。"}
                        store.save(job)
            finally:
                self._queue.task_done()


_worker = JobWorker()


def get_worker() -> JobWorker:
    return _worker
