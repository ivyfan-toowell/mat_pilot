"""定义论文实验记录、原文证据及审核状态，与材料计算数据区分保存。"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.science.composition import normalize_formula


class EvidenceQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_id: str
    quote: str = Field(min_length=1, max_length=1800)


class ExperimentCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    material_formula: str
    sample_label: str
    property_name: Literal["band_gap"]
    property_value: float = Field(ge=0)
    property_unit: Literal["eV"]
    experimental_method: str | None = None
    experimental_conditions: str | None = None
    evidence: list[EvidenceQuote] = Field(min_length=1, max_length=6)

    @field_validator("material_formula")
    @classmethod
    def formula_is_valid(cls, value: str) -> str:
        return normalize_formula(value)


class ExtractionCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    experiments: list[ExperimentCandidate] = Field(max_length=50)


class Experiment(ExperimentCandidate):
    experiment_id: UUID
    document_id: UUID
    page_number: int
    table_number: str | None = None
    source_url: str | None = None
    data_kind: Literal["paper_experimental_estimate"] = "paper_experimental_estimate"
    verification_status: Literal["evidence_matched_needs_review"] = "evidence_matched_needs_review"
    missing_fields: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    document_id: UUID
    model: str
    experiments: list[Experiment]
    rejected: list[dict[str, str | int]]
    field_issues: list[dict[str, str | int]] = Field(default_factory=list)
    context_truncated: bool
    warnings: list[str] = Field(
        default_factory=lambda: [
            "原文证据匹配不等于科学结论已核验；实验条件、样品身份与表格列对应仍需人工复核。"
        ]
    )
