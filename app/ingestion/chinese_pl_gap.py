"""Recover directly measured PL-derived optical gap from Chinese two-column PDFs.

The match requires the authors' own PL measurement, a prepared material,
the explicit photon-energy calculation and an eV value in the same column.
"""

from __future__ import annotations

import re
import unicodedata
from uuid import uuid5

from app.schemas.document import ParsedDocument
from app.schemas.experimental_knowledge import EvidenceField, EvidenceRef, ExperimentalObservation


def _normal(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace("\u00ad", "")


def extract_chinese_pl_gap(
    document: ParsedDocument, tenant_id: str
) -> tuple[list[ExperimentalObservation], list[str]]:
    results: list[ExperimentalObservation] = []
    warnings: list[str] = []
    for page in sorted({b.page_number for b in document.blocks}):
        blocks = [b for b in document.blocks if b.page_number == page and b.kind == "text"]
        for anchor in blocks:
            if not re.search(r"测试了其\s*PL\s*谱", _normal(anchor.text), re.I):
                continue
            # Reassemble the same column, rather than mixing two-column text by Y.
            peers = [
                b
                for b in blocks
                if b.bbox[1] >= anchor.bbox[1] - 2
                and b.bbox[1] <= anchor.bbox[1] + 150
                and b.bbox[0] >= anchor.bbox[0] - 15
                and b.bbox[2] <= anchor.bbox[2] + 20
            ]
            peers.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
            joined = " ".join(_normal(b.text) for b in peers)
            if "通过光子能量" not in joined or "计算得其带隙约为" not in joined:
                continue
            formula = re.search(
                r"所制备的\s*([A-Z][A-Za-z0-9\s]{2,17}?)\s*具有",
                joined,
            )
            gap = re.search(
                r"通过光子能量\s*E\s*=\s*hc\s*/\s*[λ\\u03bb].*?"
                r"计算得其带隙约为\s*(\d+(?:\.\d+)?)\s*eV",
                joined,
                re.I | re.S,
            )
            if not formula or not gap:
                continue
            species = re.sub(r"\s+", "", formula.group(1))
            if not re.fullmatch(r"(?:[A-Z][a-z]?\d*){2,6}", species):
                continue
            value = float(gap.group(1))
            if not 0 < value < 10:
                continue
            # Preserve contiguous unmodified PDF block quotes and their coordinates.
            relevant = [
                b
                for b in peers
                if re.search(
                    r"测试了其\s*PL|所制备的|通过光子能量|计算得其带隙约为|eV",
                    _normal(b.text),
                    re.I,
                )
            ]
            refs = [
                EvidenceRef(
                    document_id=document.document_id,
                    block_id=b.block_id,
                    page_number=page,
                    quote=b.text[:1800],
                )
                for b in relevant
            ]
            if not refs:
                continue
            label = f"{species} PL测量样品（由实验上下文归纳）"
            results.append(
                ExperimentalObservation(
                    tenant_id=tenant_id,
                    document_id=document.document_id,
                    sample_id=uuid5(document.document_id, f"pl-derived-{page}-{species}-{value}"),
                    local_sample_label=EvidenceField(status="derived", value=label, evidence=refs),
                    formula=EvidenceField(status="reported", value=species, evidence=refs),
                    measurement_technique=EvidenceField(
                        status="reported", value="PL", evidence=refs
                    ),
                    property_value=value,
                    property_evidence=refs,
                )
            )
            warnings.append(
                f"第 {page} 页识别到 {species} 的 PL 推算带隙 {value:g} eV；"
                "保留原文证据，样品名称从实验上下文归纳，需人工审核。"
            )
            return results, warnings
    return results, warnings
