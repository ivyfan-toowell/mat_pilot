"""提供响应式材料筛选、真实结果展示、来源查看和 CSV 导出界面。"""

from html import escape

import httpx
import pandas as pd
import streamlit as st

from ui.shared import badges, empty_state, number, page_header, post_json, request_error


@st.cache_data(ttl=120, show_spinner=False)
def query_csv(backend_url: str, query_id: str) -> bytes:
    response = httpx.get(
        f"{backend_url}/api/materials/queries/{query_id}/csv", timeout=30, trust_env=False
    )
    response.raise_for_status()
    return response.content


def render(backend_url: str) -> None:
    page_header("从材料问题开始。", "明确筛选条件，再比较有来源的计算属性。", "材料筛选")
    with st.container(key="panel_material_search"):
        formula = st.text_input(
            "化学式（可选）",
            placeholder="例如 TiO2",
            key="material_formula",
            persist_state="session",
        )
        left, right = st.columns(2)
        minimum = left.number_input(
            "带隙下限（eV）",
            min_value=0.0,
            value=1.5,
            step=0.1,
            key="material_gap_min",
            persist_state="session",
        )
        maximum = right.number_input(
            "带隙上限（eV）",
            min_value=0.0,
            value=3.0,
            step=0.1,
            key="material_gap_max",
            persist_state="session",
        )
        with st.expander("更多筛选条件"):
            elements = st.text_input(
                "必须包含的元素（逗号分隔）",
                value="O",
                key="material_elements",
                persist_state="session",
            )
            hull_max = st.number_input(
                "Energy Above Hull 上限（eV/atom）",
                min_value=0.0,
                value=0.05,
                step=0.01,
                key="material_hull",
                persist_state="session",
            )
            limit = st.number_input(
                "查询条数上限",
                min_value=1,
                max_value=100,
                value=20,
                key="material_limit",
                persist_state="session",
            )
            st.caption("条件会原样提交，不自动扩大范围。精确化学式与仅含某些元素是不同的筛选条件。")
        badges(("计算数据", "neutral"), ("Materials Project", "blue"))
        submitted = st.button(
            "查询真实材料", type="primary", icon=":material/search:", width="stretch"
        )
        st.caption("计算带隙与论文实验估计值分别呈现。按 TiO₂ 查询时，可主动调整带隙范围。")
    if submitted:
        if any(value is None for value in (minimum, maximum, hull_max, limit)):
            st.error("请完整填写带隙范围、凸包能差上限和查询条数。")
        elif minimum > maximum:
            st.error("带隙下限不能大于上限，请调整后重新查询。")
        else:
            try:
                with st.spinner("正在查询 Materials Project，请勿重复提交…"):
                    st.session_state.material_result = post_json(
                        backend_url,
                        "/api/materials/search",
                        {
                            "formula": formula.strip() or None,
                            "elements": [
                                item.strip() for item in elements.split(",") if item.strip()
                            ],
                            "band_gap_min": minimum,
                            "band_gap_max": maximum,
                            "energy_above_hull_max": hull_max,
                            "limit": int(limit),
                        },
                    )
            except (httpx.HTTPError, ValueError) as exc:
                request_error(exc, "查询未完成，请检查材料服务或稍后重试。已有结果仍保留。")
    result = st.session_state.get("material_result")
    if not result:
        empty_state(
            "先确定范围，再查看候选。",
            "填写化学式或元素条件，发起真实查询后可查看计算带隙、稳定性和完整来源。",
        )
        return
    with st.container(key="panel_material_results"):
        st.subheader(f"候选材料 · {len(result['materials'])} 条")
        st.caption("以下结果对应上一次成功提交的条件。修改输入后，请重新查询以更新结果。")
        for warning in result["warnings"]:
            st.warning(warning)
        materials = result["materials"]
        if materials:
            with st.container(key="desktop_results"):
                frame = pd.DataFrame(materials)[
                    ["material_id", "formula", "band_gap", "energy_above_hull", "crystal_system"]
                ]
                frame.columns = [
                    "材料编号",
                    "化学式",
                    "计算带隙（eV）",
                    "凸包能差（eV/atom）",
                    "晶系",
                ]
                st.dataframe(frame, hide_index=True, width="stretch")
            with st.container(key="mobile_results"):
                for material in materials:
                    st.html(
                        '<article class="mp-material-card">'
                        f"<h3>{escape(material['formula'])}</h3>"
                        '<div class="mp-material-values"><span>计算带隙<strong>'
                        f"{escape(number(material.get('band_gap'), 'eV'))}</strong></span>"
                        "<span>凸包能差<strong>"
                        f"{escape(number(material.get('energy_above_hull'), 'eV/atom'))}"
                        "</strong></span></div>"
                        f"<p>{escape(material['material_id'])}</p></article>"
                    )
        else:
            st.info("没有符合当前条件的材料。请主动调整条件后再次查询。")
        try:
            st.download_button(
                "下载结果 CSV",
                query_csv(backend_url, result["query_id"]),
                file_name=f"materials-{result['query_id']}.csv",
                mime="text/csv",
                icon=":material/download:",
                on_click="ignore",
            )
        except httpx.HTTPError:
            st.caption("CSV 暂时无法准备，请检查后端后重试。")
        with st.expander("查询条件、来源与完整属性"):
            st.caption(f"查询 ID：{result['query_id']} · 获取时间：{result['retrieved_at']}")
            st.json(result)
