"""Search, browse and recoverably delete parsed papers, ten records per page."""

from urllib.parse import urlencode

import httpx
import streamlit as st

from ui.shared import api_headers, get_json, go_to, page_header, request_error

PAGE_SIZE = 10


def _reset_page() -> None:
    st.session_state.document_catalog_offset = 0
    st.session_state.pop("delete_document_candidate", None)


def _open_document(document_id: str) -> None:
    st.session_state.pending_document_id = document_id
    go_to("论文解析")


def _change_page(offset: int) -> None:
    st.session_state.document_catalog_offset = offset
    st.session_state.pop("delete_document_candidate", None)


def _mutate(backend_url: str, document_id: str, *, restore: bool = False) -> None:
    with httpx.Client(timeout=20, trust_env=False, headers=api_headers()) as client:
        path = f"{backend_url}/api/v1/documents/{document_id}"
        response = client.post(path + "/restore") if restore else client.delete(path)
        response.raise_for_status()
    get_json.clear()
    st.session_state.pop("delete_document_candidate", None)
    if not restore:
        for key in ("active_document_id", "pending_document_id"):
            if st.session_state.get(key) == document_id:
                st.session_state.pop(key, None)
        if st.session_state.get("document", {}).get("document_id") == document_id:
            st.session_state.pop("document", None)
        st.session_state.get("saved_extractions", {}).pop(document_id, None)
    st.session_state.document_catalog_notice = "论文已恢复。" if restore else "论文已移入回收站。"
    st.rerun()


def render(backend_url: str) -> None:
    page_header("全部已解析论文", "按作者或标题查找论文，管理解析版本。", "论文管理")
    st.button("返回论文解析", icon=":material/arrow_back:", on_click=go_to, args=("论文解析",))
    notice = st.session_state.pop("document_catalog_notice", None)
    if notice:
        st.success(notice)
    scope = st.radio(
        "查看范围",
        ["已解析论文", "回收站"],
        horizontal=True,
        key="document_catalog_scope",
        on_change=_reset_page,
    )
    query = st.text_input(
        "搜索作者、论文标题或文件名",
        key="document_catalog_query",
        on_change=_reset_page,
        max_chars=200,
    ).strip()
    deleted = scope == "回收站"
    offset = st.session_state.setdefault("document_catalog_offset", 0)
    params = urlencode(
        {"limit": PAGE_SIZE, "offset": offset, "q": query, "deleted": str(deleted).lower()}
    )
    try:
        result = get_json(backend_url, "/api/v1/documents/catalog?" + params)
    except (httpx.HTTPError, ValueError) as exc:
        request_error(exc, "暂时无法读取论文列表，请稍后重试。")
        return
    total, items = result["total"], result["items"]
    if offset and offset >= total:
        _change_page(max(0, (total - 1) // PAGE_SIZE * PAGE_SIZE))
        st.rerun()
    st.caption(f"共 {total} 条记录 · 每页 {PAGE_SIZE} 条")
    if deleted:
        st.caption("删除的论文保留原文、实验记录和审核信息，可随时恢复。")
    if not items:
        st.info(
            "暂无匹配的论文。" if query else ("回收站为空。" if deleted else "尚无已解析论文。")
        )
        return
    candidate = st.session_state.get("delete_document_candidate")
    for item in items:
        document_id = item["document_id"]
        with st.container(border=True, key=f"reveal_paper_{document_id}"):
            details, actions = st.columns([5, 1])
            with details:
                st.subheader(item["title"])
                st.write("作者：" + ("、".join(item.get("authors") or []) or "待补充"))
                engine = "MinerU" if item.get("parser_engine") == "mineru" else "PyMuPDF"
                st.caption(
                    f"{item['page_count']} 页 · {engine} · 版本 {document_id[:6]} · "
                    f"{item['filename']}"
                )
            with actions:
                if deleted:
                    if st.button("恢复", key=f"restore_paper_{document_id}"):
                        try:
                            _mutate(backend_url, document_id, restore=True)
                        except (httpx.HTTPError, ValueError) as exc:
                            request_error(exc, "论文未能恢复，请稍后重试。")
                else:
                    st.button(
                        "打开",
                        key=f"open_paper_{document_id}",
                        on_click=_open_document,
                        args=(document_id,),
                    )
                    if st.button("删除", key=f"delete_paper_{document_id}"):
                        st.session_state.delete_document_candidate = document_id
                        st.rerun()
            if candidate == document_id and not deleted:
                st.warning("将这条解析记录移入回收站？仅删除当前版本，其他解析版本保留。")
                confirm, cancel = st.columns(2)
                with confirm:
                    if st.button("确认移入回收站", key=f"confirm_delete_{document_id}"):
                        try:
                            _mutate(backend_url, document_id)
                        except (httpx.HTTPError, ValueError) as exc:
                            request_error(exc, "论文未能删除，请稍后重试。")
                with cancel:
                    if st.button("取消", key=f"cancel_delete_{document_id}"):
                        st.session_state.pop("delete_document_candidate", None)
                        st.rerun()
    previous, position, following = st.columns([1, 2, 1])
    with previous:
        st.button(
            "上一页",
            disabled=offset == 0,
            on_click=_change_page,
            args=(max(0, offset - PAGE_SIZE),),
        )
    with position:
        st.write(
            f"第 {offset // PAGE_SIZE + 1} / {max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)} 页"
        )
    with following:
        st.button(
            "下一页",
            disabled=offset + PAGE_SIZE >= total,
            on_click=_change_page,
            args=(offset + PAGE_SIZE,),
        )
