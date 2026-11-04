"""提供论文上传、已有文献回读、页码证据与实验记录的响应式界面。"""

import json

import httpx
import pandas as pd
import streamlit as st

from ui.shared import (
    activate_document,
    badges,
    empty_state,
    evidence_dialog,
    get_json,
    go_to,
    number,
    page_header,
    post_json,
    request_error,
    research_context,
    safe_link,
)


def render(backend_url: str) -> None:
    page_header("把论文变成可核查的证据。", "保留原文、页码与实验记录的对应关系。", "论文解析")
    document = research_context(backend_url)
    with st.expander("上传一篇新论文", expanded=document is None):
        uploaded = st.file_uploader(
            "上传科研论文（PDF，最多 30 MB）", type=["pdf"], key="paper_upload"
        )
        with st.expander("原文链接与文献许可（可选）"):
            source = st.text_input(
                "原文链接",
                placeholder="https://doi.org/…",
                key="paper_source",
                persist_state="session",
            )
            license_name = st.text_input(
                "文献许可",
                placeholder="例如 CC BY 4.0",
                key="paper_license",
                persist_state="session",
            )
        st.caption("当前支持文本型 PDF；扫描件会明确提示需要 OCR。")
        if st.button(
            "解析论文",
            disabled=uploaded is None,
            type="primary",
            icon=":material/upload_file:",
            width="stretch",
        ):
            try:
                with st.spinner("正在提取正文、页码和表格…"):
                    response = httpx.post(
                        f"{backend_url}/api/documents",
                        files={"file": (uploaded.name, uploaded.getvalue(), "application/pdf")},
                        data={"source_url": source, "license_name": license_name},
                        timeout=180,
                        trust_env=False,
                    )
                    response.raise_for_status()
                activate_document(response.json())
            except (httpx.HTTPError, ValueError) as exc:
                request_error(exc, "文献解析失败，请检查文件内容、大小或后端状态。")
    if not document:
        empty_state(
            "从一篇真实论文开始。",
            "上传 PDF，或从上方选择已解析文献。随后可查看原文、提取实验带隙并加入知识库。",
        )
        return
    document_id = document["document_id"]
    with st.container(key="panel_document"):
        st.subheader(document["title"])
        badges((f"{document['page_count']} 页", "neutral"), ("论文原文", "blue"))
        for warning in document["warnings"]:
            st.warning(warning)
        safe_link("打开论文来源", document.get("source_url"))
        original_tab, experiments_tab = st.tabs(["原文证据", "实验记录"])
        with original_tab:
            page_number = st.selectbox(
                "查看原文页码",
                list(range(1, document["page_count"] + 1)),
                key=f"paper_page_{document_id}",
                persist_state="session",
            )
            blocks = [block for block in document["blocks"] if block["page_number"] == page_number]
            if not blocks:
                st.info("这一页没有可提取文本；扫描页面可能需要 OCR。")
            for block in blocks:
                with st.expander(
                    f"{'表格' if block['kind'] == 'table' else '正文'} · {block['block_id']}",
                    expanded=True,
                ):
                    st.text(block["text"])
                    if block.get("rows"):
                        st.dataframe(pd.DataFrame(block["rows"]), hide_index=True, width="stretch")
        with experiments_tab:
            cache = st.session_state.setdefault("saved_extractions", {})
            if document_id not in cache:
                try:
                    cache[document_id] = get_json(
                        backend_url, f"/api/documents/{document_id}/experiments"
                    )
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 404:
                        request_error(exc, "暂时无法读取已有实验记录。")
                except (httpx.HTTPError, ValueError) as exc:
                    request_error(exc, "暂时无法读取已有实验记录。")
            st.caption("下方按钮会调用大模型。已有记录可直接查看；重新提取不会自动发生。")
            if st.button(
                "提取实验带隙", key="extract_experiments", type="primary", icon=":material/science:"
            ):
                try:
                    with st.spinner("正在提取并校验实验原文…"):
                        cache[document_id] = post_json(
                            backend_url, f"/api/documents/{document_id}/extract", {}, 90
                        )
                    get_json.clear()
                except (httpx.HTTPError, ValueError) as exc:
                    request_error(exc, "实验提取未完成，原有记录仍保留。")
            extraction = cache.get(document_id)
            if extraction:
                for warning in extraction["warnings"]:
                    st.warning(warning)
                for item in extraction["experiments"]:
                    with st.container(border=True):
                        st.subheader(
                            f"{item['sample_label']} · "
                            f"{number(item['property_value'], item['property_unit'])}"
                        )
                        badges(
                            ("论文实验估计", "blue"),
                            ("原文已匹配", "green"),
                            ("待科研审核", "amber"),
                        )
                        st.caption(f"{item['material_formula']} · 第 {item['page_number']} 页")
                        with st.expander("方法与测量设置"):
                            st.write(item.get("experimental_method") or "当前记录未提取方法。")
                            st.write(
                                item.get("experimental_conditions") or "当前记录未提取测量设置。"
                            )
                        quotes = "\n\n".join(evidence["quote"] for evidence in item["evidence"])
                        if st.button(
                            "查看对应原文",
                            key=f"experiment_{item['experiment_id']}",
                            icon=":material/format_quote:",
                        ):
                            evidence_dialog(
                                item["sample_label"],
                                quotes,
                                f"第 {item['page_number']} 页",
                                item.get("source_url"),
                            )
                if not extraction["experiments"]:
                    st.info("尚无通过原文证据校验的实验记录。")
                st.download_button(
                    "下载实验记录与证据 JSON",
                    json.dumps(extraction, ensure_ascii=False, indent=2),
                    f"experiments-{document_id}.json",
                    "application/json",
                    icon=":material/download:",
                    on_click="ignore",
                )
                with st.expander("完整提取结果与拒绝原因"):
                    st.json(extraction)
            else:
                st.info("尚无已保存的实验记录。可以先检查原文，再主动执行提取。")
        with st.expander("文献来源与技术详情"):
            st.write(
                {
                    "文献 ID": document_id,
                    "文件名": document["filename"],
                    "解析时间": document["parsed_at"],
                    "许可": document.get("license"),
                }
            )
    st.button(
        "前往文献知识库", icon=":material/arrow_forward:", on_click=go_to, args=("文献知识库",)
    )
