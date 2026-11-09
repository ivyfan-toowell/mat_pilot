"""Experimental knowledge query, opt-in extraction, review, comparison and export."""
from __future__ import annotations
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from app.core.auth import PrincipalDep
from app.core.config import Settings, get_settings, tenant_data_dir
from app.core.errors import ServiceError
from app.ingestion.structured_extractor import StructuredExperimentExtractor
from app.schemas.experimental_knowledge import ComparisonReport, ExperimentalObservation
from app.services.cross_paper_report import build_analysis, render_csv, render_markdown
from app.services.document_service import DocumentService
from app.services.experimental_knowledge_store import ExperimentalKnowledgeStore

router = APIRouter(prefix="/api/v1/experimental-knowledge", tags=["experimental-knowledge"])
SettingsDep = Annotated[Settings, Depends(get_settings)]

class ExtractionResponse(BaseModel):
    run_id: UUID
    stored: int
    warnings: list[str]

class CompareRequest(BaseModel):
    observation_ids: list[UUID] = Field(min_length=2, max_length=50)

class ReviewRequest(BaseModel):
    decision: Literal["human_verified", "rejected"]
    reviewer: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=2000)

def store(settings: Settings, tenant_id: str) -> ExperimentalKnowledgeStore:
    return ExperimentalKnowledgeStore(settings, tenant_id)

@router.get("/observations", response_model=list[ExperimentalObservation])
def list_observations(settings: SettingsDep, principal: PrincipalDep,
                      document_id: UUID | None = None, formula: str | None = None,
                      status: Literal["evidence_matched_needs_review", "human_verified", "rejected"] | None = None,
                      limit: Annotated[int, Query(ge=1, le=200)] = 100,
                      offset: Annotated[int, Query(ge=0, le=100000)] = 0):
    return store(settings, principal.tenant_id).list(
        document_id=document_id, formula=formula, status=status, limit=limit, offset=offset)

@router.get("/observations/{observation_id}", response_model=ExperimentalObservation)
def get_observation(observation_id: UUID, settings: SettingsDep, principal: PrincipalDep):
    return store(settings, principal.tenant_id).get(observation_id)

@router.post("/documents/{document_id}/extract", response_model=ExtractionResponse)
def extract(document_id: UUID, settings: SettingsDep, principal: PrincipalDep):
    data_dir = tenant_data_dir(settings, principal.tenant_id)
    document = DocumentService(data_dir, settings, principal.tenant_id).load(document_id)
    records, warnings = StructuredExperimentExtractor(settings, principal.tenant_id).extract(document)
    if not records:
        # Failed/uncertain extraction does not delete previous results.
        return ExtractionResponse(run_id=UUID(int=0), stored=0, warnings=warnings or [
            "没有经过证据关系校验的实验记录，因此未入库。"])
    run_id = store(settings, principal.tenant_id).save(
        document_id, records, model=settings.llm_model)
    return ExtractionResponse(run_id=run_id, stored=len(records), warnings=warnings)

@router.post("/observations/{observation_id}/review", response_model=ExperimentalObservation)
def review(observation_id: UUID, request: ReviewRequest,
           settings: SettingsDep, principal: PrincipalDep):
    return store(settings, principal.tenant_id).review(
        observation_id, request.decision, request.note, request.reviewer)

@router.post("/compare", response_model=ComparisonReport)
def compare(request: CompareRequest, settings: SettingsDep, principal: PrincipalDep):
    knowledge = store(settings, principal.tenant_id)
    if len(set(request.observation_ids)) != len(request.observation_ids):
        raise ServiceError("duplicate_observation", "重复实验记录 ID。", 422)
    records = [knowledge.get(id_) for id_ in request.observation_ids]
    return build_analysis(records)

@router.post("/report")
def export_report(request: CompareRequest, settings: SettingsDep,
                  principal: PrincipalDep, format: Literal["markdown", "csv"] = "markdown"):
    knowledge = store(settings, principal.tenant_id)
    if len(set(request.observation_ids)) != len(request.observation_ids):
        raise ServiceError("duplicate_observation", "重复实验记录 ID。", 422)
    records = [knowledge.get(id_) for id_ in request.observation_ids]
    report = build_analysis(records)
    if format == "csv":
        return PlainTextResponse(render_csv(records), media_type="text/csv; charset=utf-8")
    return PlainTextResponse(render_markdown(report), media_type="text/markdown; charset=utf-8")
