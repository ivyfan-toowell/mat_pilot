"""Independent evidence-reference audit against the persisted ParsedDocument.

This checks copied text, block and page identity, and property numerics.
It cannot certify OCR against physical PDF pixels: human review remains required.
"""

from __future__ import annotations

import math
import re
import unicodedata

from pydantic import BaseModel, Field

from app.schemas.document import ParsedDocument
from app.schemas.experimental_knowledge import ExperimentalObservation

FIELDS = (
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
)


class EvidenceAudit(BaseModel):
    valid: bool
    document_id: str
    observation_id: str
    parser_engine: str
    checked_references: int
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _normal(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    # Chinese OCR can insert whitespace between digits and a decimal point.
    text = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", text)
    return re.sub(r"\s+", "", text).casefold()


def audit_observation(
    document: ParsedDocument, record: ExperimentalObservation
) -> EvidenceAudit:
    issues: list[str] = []
    count = 0
    if record.document_id != document.document_id:
        issues.append("document_id_mismatch")
    by_id = {block.block_id: block for block in document.blocks}
    if len(by_id) != len(document.blocks):
        issues.append("duplicate_source_block_id")

    references = [("property", ref) for ref in record.property_evidence]
    for field in FIELDS:
        references.extend((field, ref) for ref in getattr(record, field).evidence)

    for field, ref in references:
        count += 1
        block = by_id.get(ref.block_id)
        if ref.document_id != document.document_id:
            issues.append(f"{field}:cross_document_reference")
        elif block is None:
            issues.append(f"{field}:missing_source_block")
        elif block.page_number != ref.page_number:
            issues.append(f"{field}:page_mismatch")
        elif not _normal(ref.quote) or _normal(ref.quote) not in _normal(block.text):
            issues.append(f"{field}:quote_not_in_parsed_source")

    numeric_text = " ".join(ref.quote for ref in record.property_evidence)
    numbers = re.findall(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?", _normal(numeric_text))
    if not any(
        math.isclose(float(value), record.property_value, rel_tol=0, abs_tol=1e-5)
        for value in numbers
    ):
        issues.append("property:numeric_value_not_in_evidence")

    # OCR is a transcription, not a direct verification of the PDF pixels.
    warnings = (
        ["MinerU OCR 证据仅与解析文本匹配，人工审核需核对 PDF 原页及图片。"]
        if document.parser_engine == "mineru"
        else ["原文匹配不等于实验结论正确；请核对 PDF 原页。"]
    )
    if any(
        getattr(record, name).status == "derived" for name in FIELDS
    ):
        warnings.append("含系统推导的样品或实验条件，必须人工核对对应关系。")
    return EvidenceAudit(
        valid=not issues,
        document_id=str(document.document_id),
        observation_id=str(record.observation_id),
        parser_engine=document.parser_engine,
        checked_references=count,
        issues=sorted(set(issues)),
        warnings=warnings,
    )
