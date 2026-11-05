"""提供响应式文献问答、检索设置、知识库管理与可点击原文证据。"""

import json

import httpx
import streamlit as st

from ui.shared import (
    badges,
    empty_state,
    evidence_dialog,
    page_header,
    post_json,
    request_error,
    research_context,
    run_job,
)


def render(backend_url: str) -> None:
    page_header("让每个回答，都有出处。", "向论文提问，并回到原文核查。", "文献知识库")
    document = research_context(backend_url)
    with st.expander("知识库管理 · 添加当前文献"):
        if document:
            st.write(document["title"])
            st.caption("加入知识库会调用向量模型；只有点击下方按钮才会执行。")
            if st.button("将文献加入知识库", icon=":material/library_add:"):
                try:
                    with st.spinner("正在分块、向量化并保存文献…"):
                        result = run_job(
                            backend_url,
                            "/api/v1/jobs/knowledge/index",
                            {"document_id": document["document_id"]},
                            300,
                        )
                    st.success(f"已索引 {result['chunks']} 个文档块。")
                except (httpx.HTTPError, ValueError, TimeoutError, RuntimeError) as exc:
                    request_error(exc, "索引未完成，请检查数据库和向量服务。")
        else:
            st.caption("先在上方选择文献，或到论文解析工作区上传 PDF。")
    with st.container(key="panel_knowledge_question"):
        question = st.text_area(
            "向论文提问",
            placeholder="例如：碱处理时间如何影响 TiO₂ 的光学带隙？",
            key="knowledge_question",
            height=120,
            persist_state="session",
        )
        mode = st.radio(
            "模式",
            ["原文检索", "带引用回答"],
            horizontal=True,
            key="knowledge_mode",
            persist_state="session",
        )
        with st.expander("检索设置"):
            current_only = st.checkbox(
                "仅检索当前文献",
                value=True,
                disabled=document is None,
                key="knowledge_current_only",
                persist_state="session",
            )
            strategy = st.selectbox(
                "检索策略",
                ["语义检索", "关键词检索", "混合检索"],
                key="knowledge_strategy",
                persist_state="session",
            )
            rerank = st.checkbox(
                "使用通义 Rerank 重排（额外模型调用）",
                key="knowledge_rerank",
                persist_state="session",
            )
            st.caption("排序分数不代表科研置信度。带引用回答和重排会调用配置的模型。")
        scope = "当前文献" if document and current_only else "整个知识库"
        st.caption(f"{scope} · {strategy} · {'已开启重排' if rerank else '未开启重排'}")
        submitted = st.button(
            "查询知识库", type="primary", icon=":material/search:", width="stretch"
        )
    if submitted:
        if not question.strip():
            st.error("请先填写要检索或回答的问题。")
        elif not strategy:
            st.error("请选择检索策略。")
        else:
            try:
                with st.spinner("正在检索原文并检查来源，请勿重复提交…"):
                    result = post_json(
                        backend_url,
                        "/api/v1/knowledge/" + ("answer" if mode == "带引用回答" else "search"),
                        {
                            "question": question.strip(),
                            "document_id": document["document_id"]
                            if document and current_only
                            else None,
                            "retrieval_mode": {
                                "语义检索": "dense",
                                "关键词检索": "sparse",
                                "混合检索": "hybrid",
                            }[strategy],
                            "rerank": rerank,
                        },
                        120,
                    )
                st.session_state.knowledge_result = result
                st.session_state.knowledge_result_context = {
                    "document_id": document["document_id"] if document and current_only else None,
                    "scope": f"指定文献：{document['filename']}"
                    if document and current_only
                    else "全部已索引文献",
                    "strategy": strategy,
                    "rerank": rerank,
                    "mode": mode,
                }
            except (httpx.HTTPError, ValueError) as exc:
                request_error(exc, "查询未完成，请检查后端与服务配置。上次结果仍保留。")
    result = st.session_state.get("knowledge_result")
    if not result:
        empty_state(
            "从一个具体问题开始。",
            "可先检索原文，再生成带引用的回答。每条来源都保留文献、页码和原文。",
        )
        return
    st.caption(f"结果对应问题：{result['question']}")
    previous_context = st.session_state.get("knowledge_result_context", {})
    st.caption("结果范围：" + previous_context.get("scope", "以每条证据的原文定位为准"))
    current_context = {
        "document_id": document["document_id"] if document and current_only else None,
        "strategy": strategy,
        "rerank": rerank,
        "mode": mode,
    }
    if previous_context and any(
        previous_context.get(key) != value for key, value in current_context.items()
    ):
        st.info("文献范围或检索设置已变化。下方保留上次成功查询的结果，请重新查询以更新。")
    with st.container(key="panel_knowledge_result"):
        if "answer" in result:
            with st.container(key="knowledge_answer"):
                st.subheader("回答")
                st.write(result["answer"])
        sources = result.get("sources", result.get("hits", []))
        st.subheader(f"原文证据 · {len(sources)} 条")
        for warning in result.get("warnings", []):
            st.warning(warning)
        if not sources:
            st.info("现有证据不足，可以调整问题、检索范围或补充全文。")
        for index, source in enumerate(sources, 1):
            with st.expander(
                f"[{index}] 第 {source['page_number']} 页 · 阅读证据", expanded=index == 1
            ):
                badges(("论文原文", "blue"), ("需科研核查", "amber"))
                st.text(source["text"])
                if st.button(
                    f"打开原文详情 [{index}]",
                    key=f"knowledge_source_{index}",
                    icon=":material/open_in_full:",
                ):
                    evidence_dialog(
                        f"证据 [{index}]",
                        source["text"],
                        f"第 {source['page_number']} 页 · {source['block_id']}",
                        source.get("source_url"),
                    )
                with st.expander("排序与定位详情"):
                    scores = {
                        name: source[name]
                        for name in ("similarity", "sparse_score", "rrf_score", "rerank_score")
                        if source.get(name) is not None
                    }
                    st.json(
                        {
                            "document_id": source["document_id"],
                            "block_id": source["block_id"],
                            "scores": scores,
                        }
                    )
        st.download_button(
            "下载回答与证据",
            json.dumps(result, ensure_ascii=False, indent=2),
            "knowledge-result.json",
            "application/json",
            on_click="ignore",
            icon=":material/download:",
        )
        with st.expander("完整回答与引用原文"):
            st.json(result)
