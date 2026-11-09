"""Conservative source-linked enrichment for Chinese experimental-gap records.

Only extracts fields from explicit wording in the source PDF. The function never
deduces sample-specific phase, doping extent, or treatment time from a graph.
"""
from __future__ import annotations

import re
import unicodedata

from app.schemas.document import ParsedDocument, SourceBlock
from app.schemas.experimental_knowledge import EvidenceField, EvidenceRef, ExperimentalObservation


def _normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    # Older Chinese PDFs insert spaces between each Han character.
    return re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)


def _match(
    document: ParsedDocument,
    pattern: str,
    *,
    guard: str | None = None,
    allowed_pages: set[int] | None = None,
) -> EvidenceField:
    for block in document.blocks:
        if block.kind != "text" or (
            allowed_pages is not None and block.page_number not in allowed_pages
        ):
            continue
        content = _normalized(block.text)
        if guard and re.search(guard, content, re.I) is None:
            continue
        match = re.search(pattern, content, re.I)
        if not match:
            continue
        value = match.group(1)
        # If the text needed inter-character space repair, mark it derived.
        raw_normalized = unicodedata.normalize("NFKC", block.text)
        status = "reported" if value in raw_normalized else "derived"
        return EvidenceField(
            value=value,
            status=status,
            evidence=[
                EvidenceRef(
                    document_id=document.document_id,
                    block_id=block.block_id,
                    page_number=block.page_number,
                    quote=block.text[:1800],
                )
            ],
        )
    return EvidenceField()


def enrich_annealing_gap_records(
    document: ParsedDocument,
    records: list[ExperimentalObservation],
) -> list[ExperimentalObservation]:
    """Enrich optical-gap series only when explicit experimental context is found."""
    if not records:
        return records
    # Analysis evidence is local to the measured gap sequence, not Introduction.
    result_pages = {ref.page_number for record in records for ref in record.property_evidence}
    analysis = _match(document, r"(外推法)", allowed_pages=result_pages)
    transition = _match(
        document, r"(直接带隙)", guard=r"TiO2.{0,20}直接带隙",
        allowed_pages=result_pages,
    )
    technique = _match(
        document, r"(透射光谱)", guard=r"实验所得|光学带隙|外推",
        allowed_pages=result_pages,
    )
    # Preparation requires explicit method-context wording; avoid references.
    methods_pages = {page for page in range(1, min(result_pages) + 1)}
    preparation = _match(
        document, r"(离子注入)", guard=r"制备|室温|注入|薄膜",
        allowed_pages=methods_pages,
    )
    atmosphere = _match(
        document, r"(氮气)", guard=r"氮气(?:中|气氛).*?退火|退火.*?氮气",
        allowed_pages=methods_pages,
    )
    doping = _match(
        document, r"(氮掺杂)", guard=r"TiO2|薄膜",
        allowed_pages=methods_pages,
    )
    enriched = []
    for record in records:
        enriched.append(
            record.model_copy(
                update={
                    "analysis_method": analysis,
                    "transition_assumption": transition,
                    "measurement_technique": technique,
                    "preparation_method": preparation,
                    "preparation_atmosphere": atmosphere,
                    "doping": doping,
                }
            )
        )
    return enriched
