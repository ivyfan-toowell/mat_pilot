"""Sample-level experimental knowledge and cross-paper comparison workspace."""
from __future__ import annotations
import httpx
import pandas as pd
import streamlit as st
from ui.shared import api_headers, page_header, request_error

PREFIX = "/api/v1/experimental-knowledge"

def _request(backend_url: str, method: str, suffix: str, **kwargs):
    with httpx.Client(timeout=180, trust_env=False, headers=api_headers()) as client:
        response = client.request(method, f"{backend_url}{PREFIX}{suffix}", **kwargs)
        response.raise_for_status()
        return response

def render(backend_url: str) -> None:
    page_header("实验知识与跨论文对比", "按论文、样品与实验条件对照带隙；证据不足时不推断因果。", "实验知识库")
    st.caption("V0.9：仅支持人工上传且已经解析的文本 PDF。实验提取调用付费模型；自动提取不代表人工审核。")
    doc_id = st.text_input("已解析文献 UUID（可选）", placeholder="粘贴论文解析页面的 document_id")
    col1, col2 = st.columns(2)
    with col1:
        formula = st.text_input("化学式过滤（可选）", placeholder="TiO2")
    with col2:
        only_approved = st.checkbox("仅显示人工审核通过")
    if st.button("提取所选论文的结构化实验信息", disabled=not doc_id.strip()):
        try:
            with st.spinner("正在提取样品与实验条件…"):
                outcome = _request(backend_url, "POST", f"/documents/{doc_id.strip()}/extract").json()
            st.success(f"本次入库 {outcome['stored']} 条记录")
            for warning in outcome.get("warnings", []):
                st.warning(warning)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            request_error(exc, "提取失败，历史审核记录未被修改。")
    try:
        params = {"limit": 100}
        if doc_id.strip():
            params["document_id"] = doc_id.strip()
        if formula.strip():
            params["formula"] = formula.strip()
        if only_approved:
            params["status"] = "human_verified"
        items = _request(backend_url, "GET", "/observations", params=params).json()
    except (httpx.HTTPError, ValueError) as exc:
        request_error(exc, "无法读取实验知识库。")
        return
    if not items:
        st.info("当前条件下没有结构化实验记录。请先导入并提取拥有处理权限的论文。")
        return
    rows = []
    for item in items:
        rows.append({
            "observation_id": item["observation_id"],
            "document_id": item["document_id"],
            "sample": item["local_sample_label"]["value"],
            "formula": item["formula"]["value"],
            "phase": item["phase"]["value"],
            "temperature": item["preparation_temperature"]["value"],
            "technique": item["measurement_technique"]["value"],
            "band_gap_eV": item["property_value"],
            "review": item["verification_status"],
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with st.expander("查看原文证据并审核"):
        selected = st.selectbox("实验记录", items, format_func=lambda x:
                                f"{x['local_sample_label']['value']} · {x['document_id']} · {x['observation_id']}")
        for field in ("formula", "phase", "preparation_temperature", "measurement_technique",
                      "analysis_method", "transition_assumption"):
            entry = selected[field]
            st.markdown(f"**{field}**：{entry['value'] or '未提取'}")
            for ref in entry["evidence"]:
                st.caption(f"第 {ref['page_number']} 页 · {ref['block_id']}")
                st.code(ref["quote"])
        st.markdown("**光学带隙原文**")
        for ref in selected["property_evidence"]:
            st.caption(f"第 {ref['page_number']} 页 · {ref['block_id']}")
            st.code(ref["quote"])
        if selected["verification_status"] == "evidence_matched_needs_review":
            reviewer = st.text_input("审核人标识", key="reviewer_id")
            note = st.text_area("审核意见（必填）", key="review_note")
            decision = st.radio("审核结论", ["human_verified", "rejected"], horizontal=True)
            if st.button("提交人工审核", disabled=not (reviewer.strip() and note.strip())):
                try:
                    _request(backend_url, "POST", f"/observations/{selected['observation_id']}/review",
                             json={"reviewer": reviewer, "note": note, "decision": decision})
                    st.success("审核状态已保存，请刷新查看。")
                except (httpx.HTTPError, ValueError) as exc:
                    request_error(exc, "审核失败。")
    labels = {x["observation_id"]:
              f"{x['local_sample_label']['value']} · {x['document_id']} · {x['property_value']} eV"
              for x in items}
    ids = st.multiselect("选择要跨论文对比的实验记录（2–50）",
                         list(labels), format_func=lambda value: labels[value])
    if 2 <= len(ids) <= 50:
        try:
            report = _request(backend_url, "POST", "/compare",
                              json={"observation_ids": ids}).json()
            st.subheader("可比性对照")
            st.dataframe(pd.DataFrame([{
                "left": item["left_id"], "right": item["right_id"],
                "status": item["status"],
                "reasons": "; ".join(f"{r['field']}: {r['code']}" for r in item["reasons"]),
            } for item in report["comparisons"]]), hide_index=True, width="stretch")
            for fmt, mime in (("markdown", "text/markdown"), ("csv", "text/csv")):
                result = _request(backend_url, "POST", "/report",
                                  params={"format": fmt}, json={"observation_ids": ids})
                st.download_button(f"导出 {fmt.upper()}",
                                   result.content, file_name=f"matpilot_comparison.{ 'md' if fmt == 'markdown' else 'csv'}",
                                   mime=mime)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            request_error(exc, "比较或导出失败。")
