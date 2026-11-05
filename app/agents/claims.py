"""校验 Agent 结论引用、行号解析与来源边界。"""

import json
import re

from app.ingestion.extractor import normalized
from app.schemas.agent import AgentCitation, AgentClaim, AgentDraft, ToolRecord
from app.schemas.selection import SelectedAnswer
from app.services.evidence_service import copy_range, source_lines


def evidence_texts(content: str) -> list[str]:
    """Decode JSON text fields while preserving exact source wording."""
    texts = [content]

    def visit(value):
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    try:
        visit(json.loads(content))
    except ValueError:
        pass
    return texts


def validate_agent_claims(draft: AgentDraft, records: list[ToolRecord]) -> None:
    sources = {record.source_id: record for record in records if record.status == "ok"}
    for claim in draft.claims:
        quotes = "\n".join(citation.quote for citation in claim.citations)
        method_pattern = (
            r"(?<![A-Za-z0-9])(?:DFT\s*\+\s*U|GGA\s*\+\s*U|GGA|PBEsol|PBE|"
            r"HSE06|HSE|r2SCAN|(?-i:SCAN)|LDA|B3LYP|GW)(?![A-Za-z0-9])"
        )
        for method in re.findall(method_pattern, claim.text, flags=re.I):
            if not re.search(
                r"(?<![A-Za-z0-9])" + re.escape(method) + r"(?![A-Za-z0-9])", quotes, flags=re.I
            ):
                raise ValueError(
                    f"引文没有明确支持计算方法 {method}。"
                    "请仅说明数据属于计算结果，不要指定未报告的泛函。"
                )
        if re.search(
            r"\bDFT\b|first[- ]principles|第一性原理", claim.text, flags=re.I
        ) and not re.search(
            r"\bDFT\b|density functional|first[- ]principles|第一性原理|密度泛函",
            quotes,
            flags=re.I,
        ):
            raise ValueError(
                "第一性原理或 DFT 归因必须有明确的来源引用；"
                "仅凭 data_kind=computed 不能确定计算方法。"
            )
        if all(
            sources.get(citation.source_id)
            and sources[citation.source_id].name == "search_academic_papers"
            for citation in claim.citations
        ) and re.search(
            r"\d[\d.,]*\s*(?:meV|eV(?:/atom)?|nm|°C|℃|cm[-−]1|m[2²]/g)(?![a-zA-Z])", claim.text
        ):
            raise ValueError(
                "仅有元数据引用不能证实实验测量值。请引用已解析全文证据，或删除测量值论断。"
            )
        text = normalized(claim.text).lower()
        scoped = any(
            phrase in re.sub(r"\s+", "", text)
            for phrase in (
                "当前检索",
                "已检索",
                "所提供的片段",
                "当前工具",
                "工具输出",
                "提取记录",
                "providedexcerpt",
                "retrievedevidence",
                "availableexcerpt",
            )
        )
        absence = re.search(
            r"(?:原文|论文|全文|研究)[^。；]{0,160}(?:未(?:曾|明确|直接)?"
            r"(?:说明|提供|报告|声明|提及|给出|披露|讨论|描述|列出|建立|指出)|"
            r"没有(?:明确)?(?:说明|提供|报告|声明|提及|给出|讨论|描述)|缺乏|缺少)",
            text,
        )
        if (
            absence
            and not scoped
            and not any(text in normalized(citation.quote).lower() for citation in claim.citations)
        ):
            raise ValueError(
                "片段不能证明论文全文缺失某项信息。请将信息缺失的说明限定为所提供的工具输出或片段。"
            )
        for citation in claim.citations:
            if citation.source_id not in sources:
                raise ValueError("引用指向不存在或执行失败的工具来源。")
            if not any(
                normalized(citation.quote) in normalized(text)
                for text in evidence_texts(sources[citation.source_id].content)
            ):
                raise ValueError("在工具来源中未找到该引文。")


def source_text(content: str) -> str:
    # One continuous line numbering per tool avoids confusing JSON and field-local lines.
    return "\n\n".join(evidence_texts(content))


def source_context(content: str) -> dict:
    text = source_text(content)
    ranges = []
    offset = 0
    for excerpt in evidence_texts(content):
        start = len(text[:offset].splitlines()) + 1
        if excerpt.strip():
            window_start = start
            size = 0
            for index, line in enumerate(excerpt.splitlines(), start):
                if len(line) > 3000:
                    if size:
                        ranges.append({"start_line": window_start, "end_line": index - 1})
                    window_start, size = index + 1, 0
                    continue
                if size and size + len(line) + 1 > 2000:
                    ranges.append({"start_line": window_start, "end_line": index - 1})
                    window_start, size = index, 0
                size += len(line) + 1
            if 0 < size <= 3000:
                ranges.append(
                    {"start_line": window_start, "end_line": start + len(excerpt.splitlines()) - 1}
                )
        offset += len(excerpt) + 2
    field_ranges = []
    for index, line in enumerate(content.splitlines(), 1):
        if match := re.match(
            r'\s*"(material_id|formula|band_gap|energy_above_hull|band_gap_min|band_gap_max|'
            r"energy_above_hull_max|sample_label|property_value|property_unit|data_kind|"
            r'experimental_method|measurement_conditions|verification_status)"\s*:',
            line,
        ):
            if any(interval["start_line"] <= index <= interval["end_line"] for interval in ranges):
                field_ranges.append(
                    {"field": match.group(1), "start_line": index, "end_line": index}
                )
    return {"lines": source_lines(text), "allowed_ranges": ranges, "field_ranges": field_ranges}


def resolve_answer(selected: SelectedAnswer, records: list[ToolRecord]) -> AgentDraft:
    sources = {
        record.source_id: source_text(record.content) for record in records if record.status == "ok"
    }
    ranges = {
        record.source_id: source_context(record.content)["allowed_ranges"]
        for record in records
        if record.status == "ok"
    }
    claims = []
    for claim in selected.claims:
        citations = []
        for citation in claim.citations:
            text = sources.get(citation.source_id, "")
            try:
                if not any(
                    interval["start_line"]
                    <= citation.start_line
                    <= citation.end_line
                    <= interval["end_line"]
                    for interval in ranges.get(citation.source_id, [])
                ):
                    raise ValueError("引用超出了允许的证据区间。")
                citations.append(
                    AgentCitation(
                        source_id=citation.source_id,
                        quote=copy_range(text, citation),
                    )
                )
            except ValueError as exc:
                raise ValueError(
                    f"T{citation.source_id} 第 {citation.start_line}–{citation.end_line} 行："
                    f"{exc} 请从 allowed_ranges 中选择多条更短的引用。"
                ) from exc
        claims.append(AgentClaim(text=claim.text, citations=citations))
    draft = AgentDraft(claims=claims)
    validate_agent_claims(draft, records)
    return draft


