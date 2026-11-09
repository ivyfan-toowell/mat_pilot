"""Evidence-conservative Chinese prose temperature/band-gap series extraction.

Only handles author-reported experimental optical-gap sequences with explicit
start/end annealing temperatures and a corresponding ordered value list.
Intermediate temperature labels are derived and require human verification.
"""
from __future__ import annotations

import re
import unicodedata
from uuid import uuid5

from app.schemas.document import ParsedDocument
from app.schemas.experimental_knowledge import EvidenceField, EvidenceRef, ExperimentalObservation


def _normal(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace("\u00ad", "")


def extract_chinese_gap_series(
    document: ParsedDocument, tenant_id: str
) -> tuple[list[ExperimentalObservation], list[str]]:
    result: list[ExperimentalObservation] = []
    warnings: list[str] = []
    # The source PDF parser may have split a sentence across separate blocks.
    pages = sorted({block.page_number for block in document.blocks})
    for page in pages:
        blocks = [
            b for b in document.blocks if b.page_number == page and b.kind == "text"
        ]
        for index, block in enumerate(blocks):
            # Require experimental context and a precise association phrase.
            if "退火温度从" not in _normal(block.text):
                continue
            selected = blocks[index : index + 2]
            combined = " ".join(_normal(b.text) for b in selected)
            match = re.search(
                r"退火温度从\s*(\d{2,4})\s*℃\s*增加到\s*(\d{2,4})\s*℃"
                r".{0,75}?所对应的样品光学带隙分别为\s*"
                r"((?:\d+(?:\.\d+)?,?\s*){2,12})\s*eV",
                combined,
                re.I,
            )
            if not match or "所对应的样品" not in combined:
                continue
            if not any(
                "实验所得" in _normal(b.text) and "透射光谱" in _normal(b.text)
                for b in blocks[max(0, index - 7) : index + 1]
            ):
                continue
            start, end = int(match.group(1)), int(match.group(2))
            values = [float(v) for v in re.findall(r"\d+(?:\.\d+)?", match.group(3))]
            if not 2 <= len(values) <= 12 or end <= start:
                continue
            steps = len(values) - 1
            if (end - start) % steps != 0 or (end - start) // steps not in {25, 50, 100, 200}:
                continue
            if any(not 0 < value < 10 for value in values):
                continue
            identity = next(
                (b for b in blocks[max(0, index - 7) : index + 1]
                 if re.search(r"TiO2", _normal(b.text), re.I)),
                None,
            )
            if identity is None:
                continue

            def evidence(source) -> EvidenceRef:
                return EvidenceRef(
                    document_id=document.document_id,
                    block_id=source.block_id,
                    page_number=source.page_number,
                    quote=source.text[:1800],
                )

            refs = [evidence(b) for b in selected]
            formula_ref = evidence(identity)
            for offset, value in enumerate(values):
                temp = start + offset * (end - start) // steps
                label = f"退火 {temp}℃（按数据序列推导）"
                result.append(
                    ExperimentalObservation(
                        tenant_id=tenant_id,
                        document_id=document.document_id,
                        sample_id=uuid5(
                            document.document_id, f"derived-anneal-series-{page}-{temp}"
                        ),
                        local_sample_label=EvidenceField(
                            status="derived", value=label, evidence=refs
                        ),
                        formula=EvidenceField(
                            status="reported", value="TiO2", evidence=[formula_ref]
                        ),
                        preparation_temperature=EvidenceField(
                            status="derived", value=f"{temp}℃", evidence=refs
                        ),
                        property_value=value,
                        property_evidence=refs,
                    )
                )
            warnings.append(
                f"第 {page} 页提取 {len(values)} 个光学带隙；温度与数值逐项对应关系"
                "依据起止温度和数据顺序推导，需人工核对原文图表后批准。"
            )
            return result, warnings
    return result, warnings
