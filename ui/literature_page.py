"""提供统一样式的论文发现、筛选、元数据卡片及原文入口。"""

import json
from datetime import date

import httpx
import streamlit as st

from ui.shared import badges, empty_state, go_to, page_header, post_json, request_error, safe_link


def render(backend_url: str) -> None:
    page_header("发现相关论文。", "检索元数据，找到全文入口，再建立可核查的证据。", "论文发现")
    with st.container(key="panel_literature_search"):
        query = st.text_input(
            "论文关键词或 DOI",
            placeholder="TiO2 oxygen vacancies photocatalysis",
            key="literature_query",
            persist_state="session",
        )
        with st.expander("年份、开放获取与排序"):
            restrict_years = st.checkbox(
                "限定发表年份", key="literature_years", persist_state="session"
            )
            left, right = st.columns(2)
            year_from = left.number_input(
                "起始年份",
                min_value=1600,
                max_value=2100,
                value=2020,
                disabled=not restrict_years,
                key="literature_from",
                persist_state="session",
            )
            year_to = right.number_input(
                "结束年份",
                min_value=1600,
                max_value=2100,
                value=date.today().year,
                disabled=not restrict_years,
                key="literature_to",
                persist_state="session",
            )
            open_access = st.checkbox(
                "仅开放获取", value=True, key="literature_open", persist_state="session"
            )
            ordering = st.selectbox(
                "结果排序",
                ["相关性", "最新发表", "被引次数"],
                key="literature_order",
                persist_state="session",
            )
            limit = st.number_input(
                "论文条数上限",
                min_value=1,
                max_value=20,
                value=5,
                key="literature_limit",
                persist_state="session",
            )
        submitted = st.button(
            "检索在线论文", type="primary", icon=":material/search:", width="stretch"
        )
        st.caption("英文科研关键词通常更适合国际文献检索，也可直接粘贴 DOI。")
    if submitted:
        if not query.strip():
            st.error("请先输入关键词或 DOI。")
        elif limit is None or (restrict_years and (year_from is None or year_to is None)):
            st.error("请完整填写论文条数和需要限定的年份。")
        elif restrict_years and year_from > year_to:
            st.error("起始年份不能晚于结束年份。")
        else:
            try:
                with st.spinner("正在检索 OpenAlex 元数据…"):
                    st.session_state.literature_result = post_json(
                        backend_url,
                        "/api/v1/literature/search",
                        {
                            "query": query.strip(),
                            "year_from": int(year_from) if restrict_years else None,
                            "year_to": int(year_to) if restrict_years else None,
                            "open_access_only": open_access,
                            "sort": {
                                "相关性": "relevance",
                                "最新发表": "newest",
                                "被引次数": "citations",
                            }[ordering],
                            "limit": int(limit),
                        },
                        100,
                    )
            except (httpx.HTTPError, ValueError) as exc:
                request_error(exc, "在线检索未完成，请检查网络或服务配置。已有结果仍保留。")
    result = st.session_state.get("literature_result")
    if not result:
        empty_state(
            "先找到论文，再核查全文。",
            "搜索关键词或 DOI，查看发表信息与访问链接。在线元数据不能替代已解析全文证据。",
        )
        return
    with st.container(key="literature_results"):
        st.subheader(f"论文结果 · {len(result['papers'])} 条")
        st.caption(f"OpenAlex 匹配 {result['matched_count']} 条 · 结果对应上次成功提交的条件")
        for warning in result["warnings"]:
            st.warning(warning)
        for index, paper in enumerate(result["papers"], 1):
            with st.container(key=f"panel_paper_{index}"):
                badges(
                    (str(paper.get("publication_year") or "年份未知"), "neutral"),
                    ("在线元数据", "blue"),
                    (paper.get("oa_status") or "开放状态未知", "neutral"),
                )
                st.subheader(paper["title"] or "标题缺失")
                st.caption(
                    f"{paper.get('venue') or '发表载体未提供'} · "
                    f"{paper.get('work_type') or '类型未提供'}"
                )
                st.write("作者：" + ("；".join(paper["authors"]) or "未提供"))
                if paper["authors_truncated"]:
                    st.caption("仅展示前 30 位作者。")
                st.caption(f"DOI：{paper['doi'] or '未提供'}")
                if paper["is_retracted"]:
                    st.error("该论文被标记为已撤稿，请核查原始撤稿声明。")
                with st.container(horizontal=True):
                    safe_link("打开 DOI", paper.get("doi_url"), key=f"doi-{index}")
                    safe_link("论文页面", paper.get("landing_page_url"), key=f"landing-{index}")
                    safe_link("开放获取 PDF", paper.get("pdf_url"), key=f"pdf-{index}")
                with st.expander("访问许可与更多元数据"):
                    st.caption(f"链接许可：{paper.get('license') or '未提供，请核查原文'}")
                    cited = paper["cited_by_count"]
                    st.caption(
                        f"被引次数：{cited if cited is not None else '未知'}（不代表论文质量）"
                    )
                    safe_link("查看 OpenAlex 记录", paper["openalex_id"], key=f"oa-{index}")
        if not result["papers"]:
            st.info("没有匹配论文。请主动调整关键词或筛选条件，不会自动放宽范围。")
        st.info("确认许可并取得 PDF 后，可前往论文解析工作区上传全文。")
        st.button(
            "前往论文解析", on_click=go_to, args=("论文解析",), icon=":material/arrow_forward:"
        )
        st.download_button(
            "下载论文元数据 JSON",
            json.dumps(result, ensure_ascii=False, indent=2),
            f"literature-{result['query_id']}.json",
            "application/json",
            on_click="ignore",
            icon=":material/download:",
        )
