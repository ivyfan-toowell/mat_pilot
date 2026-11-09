"""Deterministic, source-attributed cross-paper summaries and exports."""
from __future__ import annotations
import csv
from io import StringIO
from app.schemas.experimental_knowledge import ComparisonReport, ExperimentalObservation
from app.services.experimental_comparison import compare_observations

def build_analysis(records: list[ExperimentalObservation]) -> ComparisonReport:
    return compare_observations(records)

def _safe(value: str | None) -> str:
    return (value or "未提取").replace("|", r"\|").replace("\n", " ")

def render_markdown(report: ComparisonReport) -> str:
    lines = [
        "# MatPilot 跨论文实验光学带隙对照",
        "",
        "> 自动生成的证据整理。样品工艺与性能差异不构成因果证明；请人工复核。",
        "",
        "| 文献 UUID | 样品 | 化学式 | 晶相 | 制备温度 | 测量技术 | 拟合方法 | 实验光学带隙 (eV) | 审核 |",
        "|---|---|---|---|---|---|---|---:|---|",
    ]
    for r in report.observations:
        lines.append("| " + " | ".join((
            str(r.document_id), _safe(r.local_sample_label.value),
            _safe(r.formula.value), _safe(r.phase.value),
            _safe(r.preparation_temperature.value), _safe(r.measurement_technique.value),
            _safe(r.analysis_method.value), str(r.property_value),
            r.verification_status,
        )) + " |")
    lines.extend(("", "## 两两可比性（规则判断）", ""))
    index = {r.observation_id: r for r in report.observations}
    for p in report.comparisons:
        l, r = index[p.left_id], index[p.right_id]
        lines.append(f"- {l.document_id}/{l.local_sample_label.value} vs "
                     f"{r.document_id}/{r.local_sample_label.value}：**{p.status}**；"
                     + "；".join(f"{reason.field}: {reason.code}" for reason in p.reasons))
    lines.extend(("", "## 原文证据", ""))
    for record in report.observations:
        lines.append(f"### {record.document_id} / {record.local_sample_label.value}")
        for field in ("local_sample_label", "formula", "phase", "doping",
                      "preparation_method", "preparation_temperature", "preparation_time",
                      "preparation_atmosphere", "measurement_technique", "analysis_method",
                      "transition_assumption", "measurement_conditions"):
            value = getattr(record, field)
            if value.status == "reported":
                for source in value.evidence:
                    lines.append(f"- {field}: {value.value} "
                                 f"（第 {source.page_number} 页，{source.block_id}）"
                                 f" 原文：{source.quote.strip()[:260]}")
        for source in record.property_evidence:
            lines.append(f"- optical_band_gap={record.property_value} eV "
                         f"（第 {source.page_number} 页，{source.block_id}）"
                         f" 原文：{source.quote.strip()[:260]}")
    lines.extend(("", "## 结论边界", "",
                  "本报告不自动推断工艺参数与光学带隙的因果关系。"
                  "任何缺失数据均表示当前未提取到，不代表论文未报告。"))
    return "\n".join(lines) + "\n"

def render_csv(records: list[ExperimentalObservation]) -> str:
    file = StringIO()
    writer = csv.writer(file)
    writer.writerow(("document_id", "observation_id", "sample", "formula", "phase",
                     "preparation_temperature", "measurement_technique", "analysis_method",
                     "transition_assumption", "optical_band_gap_eV", "verification_status"))
    for r in records:
        writer.writerow((str(r.document_id), str(r.observation_id),
                         r.local_sample_label.value, r.formula.value, r.phase.value,
                         r.preparation_temperature.value, r.measurement_technique.value,
                         r.analysis_method.value, r.transition_assumption.value,
                         r.property_value, r.verification_status))
    return file.getvalue()
