"""Evidence-backed sample-level observations for experimental optical gaps."""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: UUID
    block_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=1800)


class EvidenceField(BaseModel):
    value: str | None = None
    status: Literal["reported", "not_extracted", "ambiguous"] = "not_extracted"
    evidence: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def verify(self):
        if self.status == "reported" and (not self.value or not self.evidence):
            raise ValueError("reported field requires value and evidence")
        if self.status == "not_extracted" and (self.value is not None or self.evidence):
            raise ValueError("missing field must not have invented evidence")
        if self.status == "ambiguous" and self.value is not None:
            raise ValueError("ambiguous field cannot select a value")
        return self


class ExperimentalObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    observation_id: UUID = Field(default_factory=uuid4)
    tenant_id: str = Field(min_length=1)
    document_id: UUID
    sample_id: UUID = Field(default_factory=uuid4)
    local_sample_label: EvidenceField
    formula: EvidenceField
    phase: EvidenceField = Field(default_factory=EvidenceField)
    doping: EvidenceField = Field(default_factory=EvidenceField)
    preparation_method: EvidenceField = Field(default_factory=EvidenceField)
    preparation_temperature: EvidenceField = Field(default_factory=EvidenceField)
    preparation_time: EvidenceField = Field(default_factory=EvidenceField)
    preparation_atmosphere: EvidenceField = Field(default_factory=EvidenceField)
    measurement_technique: EvidenceField = Field(default_factory=EvidenceField)
    analysis_method: EvidenceField = Field(default_factory=EvidenceField)
    transition_assumption: EvidenceField = Field(default_factory=EvidenceField)
    measurement_conditions: EvidenceField = Field(default_factory=EvidenceField)
    property_name: Literal["optical_band_gap"] = "optical_band_gap"
    property_value: float = Field(ge=0)
    property_unit: Literal["eV"] = "eV"
    property_evidence: list[EvidenceRef] = Field(min_length=1)
    verification_status: Literal["evidence_matched_needs_review", "human_verified", "rejected"] = (
        "evidence_matched_needs_review"
    )
    value_kind: Literal["paper_experimental_estimate"] = "paper_experimental_estimate"
    extraction_run_id: UUID | None = None

    @model_validator(mode="after")
    def verify_sources(self):
        if self.local_sample_label.status != "reported" or self.formula.status != "reported":
            raise ValueError("sample and formula require cited identity")
        refs = list(self.property_evidence)
        for field in (
            "local_sample_label",
            "formula",
            "phase",
            "doping",
            "preparation_method",
            "preparation_temperature",
            "preparation_time",
            "preparation_atmosphere",
            "measurement_technique",
            "analysis_method",
            "transition_assumption",
            "measurement_conditions",
        ):
            refs.extend(getattr(self, field).evidence)
        if any(ref.document_id != self.document_id for ref in refs):
            raise ValueError("cross-document evidence forbidden")
        return self


class ComparisonReason(BaseModel):
    code: str
    field: str
    detail: str


class PairComparison(BaseModel):
    left_id: UUID
    right_id: UUID
    status: Literal["incompatible", "insufficient_evidence", "caution", "comparable"]
    reasons: list[ComparisonReason]
    human_review_required: bool = True


class ComparisonReport(BaseModel):
    property_name: Literal["optical_band_gap"] = "optical_band_gap"
    observations: list[ExperimentalObservation]
    comparisons: list[PairComparison]
    warnings: list[str] = Field(
        default_factory=lambda: [
            "Evidence compatibility is not evidence of causation.",
            "Results require independent scientific review.",
        ]
    )
