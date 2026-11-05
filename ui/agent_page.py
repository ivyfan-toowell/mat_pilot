"""提供科研助手提问、按名称回读历史任务、引用详情及协作执行记录。"""

import json

import httpx
import streamlit as st

from ui.shared import (
    badges,
    empty_state,
    evidence_dialog,
    get_json,
    page_header,
    request_error,
    research_context,
    run_job,
)

SOURCE_TOOLS = {
    "材料数据库": "search_materials",
    "文献知识库": "search_papers",
    "实验记录": "read_experiments",
    "在线论文元数据": "search_academic_papers",
}
TOOL_LABELS = {
    "search_materials": "材料筛选",
    "get_material_details": "材料详情",
    "get_structure": "晶体结构",
    "compare_materials": "材料比较",
    "search_papers": "全文证据检索",
    "read_experiments": "实验记录",
    "search_academic_papers": "在线论文元数据",
}


def render(backend_url: str) -> None:
    page_header("把问题交给科研助手。", "先收集证据，再分析与复核。结果始终保留来源。", "科研助手")
    document = research_context(backend_url)
    with st.container(key="panel_agent_question"):
        question = st.text_area(
            "科研问题",
            placeholder="例如：比较 TiO₂ 的计算带隙与论文实验估计，并说明来源与局限。",
            height=140,
            key="agent_question",
            persist_state="session",
        )
        with st.expander("执行方式与必须来源"):
            workflow = st.selectbox(
                "执行流程",
                ["自动路由", "单 Agent", "多角色协作"],
                key="agent_workflow",
                persist_state="session",
            )
            required_sources = st.multiselect(
                "本任务必须完成的资料来源（可选）",
                list(SOURCE_TOOLS),
                key="agent_sources",
                persist_state="session",
            )
            st.caption(
                "自动路由按任务决定是否协作。指定实验记录时，需要先选择已提取实验信息的文献。"
            )
        st.caption("点击执行才会调用配置的大模型；复杂任务可能需要数分钟。")
        submitted = st.button(
            "执行科研任务", type="primary", icon=":material/auto_awesome:", width="stretch"
        )
    if submitted:
        if not question.strip():
            st.error("请先描述需要完成的科研问题。")
        elif not workflow:
            st.error("请选择执行流程。")
        elif "实验记录" in required_sources and not document:
            st.error("请先选择文献，以读取对应的实验记录。")
        else:
            try:
                with st.spinner("正在收集资料、分析并校验引用，请勿重复提交…"):
                    result = run_job(
                        backend_url,
                        "/api/v1/jobs/agent",
                        {
                            "question": question.strip(),
                            "document_id": document["document_id"] if document else None,
                            "workflow_mode": {
                                "单 Agent": "single",
                                "自动路由": "auto",
                                "多角色协作": "collaborative",
                            }[workflow],
                            "required_tools": [SOURCE_TOOLS[source] for source in required_sources],
                        },
                        600,
                    )
                st.session_state.agent_result = result
                st.session_state.agent_history_loaded = False
                get_json.clear()
            except (httpx.HTTPError, ValueError, TimeoutError, RuntimeError) as exc:
                request_error(exc, "任务未完成，请检查服务配置；已有任务结果仍保留。")
    with st.expander("历史任务 · 无需再次调用模型"):
        try:
            history = get_json(backend_url, "/api/v1/agent/runs")
        except (httpx.HTTPError, ValueError):
            history = []
            st.caption("暂时无法读取任务列表，可在下方按任务 ID 回读。")
        lookup = {item["run_id"]: item for item in history}
        selected = st.selectbox(
            "选择历史任务",
            [None, *lookup],
            format_func=lambda value: (
                "选择已完成的任务"
                if value is None
                else (
                    f"{lookup[value]['question'][:65]} · "
                    f"{lookup[value]['created_at'][:16].replace('T', ' ')}"
                )
            ),
            key="history_selection",
            persist_state="session",
            placeholder="选择已完成的任务",
        )
        manual = st.text_input("历史任务 ID（可选）", key="history_manual", persist_state="session")
        run_id = manual.strip() or selected
        if st.button("读取已保存任务", disabled=not run_id, icon=":material/history:"):
            try:
                st.session_state.agent_result = get_json(
                    backend_url, f"/api/v1/agent/runs/{run_id}"
                )
                st.session_state.agent_history_loaded = True
            except (httpx.HTTPError, ValueError) as exc:
                request_error(exc, "无法读取任务，请检查任务 ID 和后端状态。")
    result = st.session_state.get("agent_result")
    if not result:
        empty_state(
            "让结论与证据一起呈现。",
            "描述一个具体问题，或回读已完成任务。页面切换和历史回读不会自动重跑模型。",
        )
        return
    with st.container(key="panel_agent_result"):
        if st.session_state.get("agent_history_loaded"):
            st.caption("已保存任务：按当时工具证据呈现；当前文献选择不会改写这一结果。")
        status = {
            "answered": "已生成",
            "insufficient_evidence": "证据不足",
            "limit_reached": "达到调用限制",
        }.get(result["status"], result["status"])
        badges(
            (status, "green" if result["status"] == "answered" else "amber"),
            (
                "多角色协作" if result.get("workflow_mode") == "collaborative" else "单智能体",
                "neutral",
            ),
        )
        st.caption(f"任务问题：{result['question']}")
        with st.container(key="agent_answer"):
            st.subheader("结论")
            st.write(result["answer"])
        for warning in result.get("warnings", []):
            st.warning(warning)
        if result.get("routing_reason"):
            st.caption(result["routing_reason"])
        st.subheader("对应原文")
        for index, claim in enumerate(result.get("claims", []), 1):
            with st.expander(f"结论 {index} · 引用证据"):
                st.write(claim["text"])
                for citation_index, citation in enumerate(claim["citations"]):
                    st.text(citation["quote"])
                    if st.button(
                        f"打开原文 [T{citation['source_id']}]",
                        key=f"agent_quote_{index}_{citation_index}",
                        icon=":material/format_quote:",
                    ):
                        evidence_dialog(
                            f"结论 {index} · T{citation['source_id']}",
                            citation["quote"],
                            "来自本任务已保存的工具记录",
                        )
        with st.expander("工具轨迹与执行详情"):
            st.caption(f"任务 ID：{result['run_id']} · 创建时间：{result['created_at']}")
            for tool in result["tools"]:
                with st.expander(
                    f"[T{tool['source_id']}] {TOOL_LABELS.get(tool['name'], tool['name'])} · "
                    f"{'已完成' if tool['status'] == 'ok' else '未完成'}"
                ):
                    st.json(tool["arguments"])
                    st.text(tool["content"])
        if result.get("collaboration"):
            with st.expander("协作计划、角色执行与 Reviewer 复核"):
                collaboration = result["collaboration"]
                st.caption(
                    f"模型调用 {collaboration['model_calls']} 次 · "
                    f"工具调用 {collaboration['tool_calls']} 次"
                )
                for step in collaboration["plan"]["steps"]:
                    st.write(
                        f"{'材料专家' if step['role'] == 'materials' else '文献专家'}："
                        f"{step['goal']}"
                    )
                st.json(collaboration)
        st.download_button(
            "下载任务与证据 JSON",
            json.dumps(result, ensure_ascii=False, indent=2),
            f"agent-{result['run_id']}.json",
            "application/json",
            on_click="ignore",
            icon=":material/download:",
        )
        with st.expander("完整结论与原文引文"):
            st.json(result["claims"])
