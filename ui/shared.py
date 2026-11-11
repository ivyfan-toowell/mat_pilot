"""提供统一主题、双端导航、文献上下文、来源弹窗和界面请求辅助功能。"""

import os
import time
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import streamlit as st


def api_headers() -> dict[str, str]:
    key = os.getenv("MATPILOT_API_KEY", "").strip()
    return {"Authorization": f"Bearer {key}"} if key else {}


WORKSPACES = {
    "材料筛选": ("materials", "tune"),
    "论文发现": ("discovery", "search"),
    "论文解析": ("documents", "description"),
    "文献知识库": ("knowledge", "local_library"),
    "科研助手": ("assistant", "auto_awesome"),
    "实验知识库": ("experimental", "table_view"),
}


def go_to(workspace: str) -> None:
    st.session_state.workspace = workspace


def setup_shell(backend_url: str) -> str:
    st.set_page_config(
        page_title="MatPilot · 材料科研工作台", page_icon=":material/science:", layout="wide"
    )
    st.html(
        "<style>" + Path(__file__).with_name("theme.css").read_text(encoding="utf-8") + "</style>"
    )
    current = st.session_state.setdefault("workspace", "材料筛选")
    with st.container(key="navigation"):
        st.html(
            '<div class="mp-brand"><span class="mp-brand-symbol">M</span>MatPilot</div>'
            '<div class="mp-brand-caption">材料与光电科研工作台</div>'
        )
        with st.container(key="navigation_links", gap="small"):
            for label, (name, icon) in WORKSPACES.items():
                with st.container(key=f"nav_entry_{'active_' if label == current else ''}{name}"):
                    st.button(
                        label,
                        key=f"nav_{name}",
                        icon=f":material/{icon}:",
                        width="stretch",
                        type="tertiary",
                        on_click=go_to,
                        args=(label,),
                    )
        motion_enabled = st.toggle(
            "页面动效",
            value=True,
            key="motion_enabled",
            help="点击进入工作区时，卡片立即从下方向上平滑到位。",
        )
        st.html('<div class="mp-navigation-note">从材料问题<br>到可核查的证据</div>')
    # A distinct name per workspace restarts CSS entry animations on navigation,
    # including when Streamlit reuses an existing DOM container. No timers or JS.
    stage = WORKSPACES.get(current, ("catalog", ""))[0]
    animation = f"mp-enter-{stage} 620ms cubic-bezier(.22,.61,.36,1) 0s both"
    st.html(
        "<style>"
        f"@keyframes mp-enter-{stage} {{"
        "from { transform:translateY(34px); } to { transform:none; }}"
        f".st-key-workspace_stage_{stage} {{"
        f"--mp-entry-animation:{animation if motion_enabled else 'none'};"
        "}</style>"
    )
    try:
        status = service_status(backend_url)
        ready = status.get("status") == "ready"
        label = "后端就绪" if ready else "部分服务待就绪"
    except (httpx.HTTPError, ValueError):
        ready, label = False, "后端暂不可用"
    st.html(
        '<header class="mp-appbar"><span>研究工作台 '
        f'<span class="mp-breadcrumb">/ {escape(current)}</span></span>'
        f'<span class="mp-service {"is-ready" if ready else "is-pending"}">'
        f'<span aria-hidden="true">●</span> {label}</span></header>'
    )
    if not ready:
        st.warning("部分服务尚未就绪。可以继续查看已有内容；新查询失败时请检查后端与数据库。")
        if st.button("重新检查服务", key="retry_service", icon=":material/refresh:"):
            service_status.clear()
            get_json.clear()
            st.rerun()
    return current


def page_header(title: str, description: str, category: str) -> None:
    st.html(
        f'<div class="mp-page-heading"><div class="mp-eyebrow">{escape(category)}</div>'
        f"<h1>{escape(title)}</h1><p>{escape(description)}</p></div>"
    )


def badges(*items: tuple[str, str]) -> None:
    st.html(
        '<div class="mp-tags">'
        + "".join(
            f'<span class="mp-tag mp-tag-{escape(kind)}">{escape(text)}</span>'
            for text, kind in items
        )
        + "</div>"
    )


def empty_state(title: str, description: str) -> None:
    st.html(
        '<section class="mp-empty"><div class="mp-empty-mark" aria-hidden="true">◇</div>'
        f"<h3>{escape(title)}</h3><p>{escape(description)}</p></section>"
    )


@st.cache_data(ttl=10, show_spinner=False)
def service_status(backend_url: str) -> dict:
    with httpx.Client(trust_env=False, timeout=4) as client:
        response = client.get(f"{backend_url}/health/ready")
        if response.status_code not in {200, 503}:
            response.raise_for_status()
        return response.json()


@st.cache_data(ttl=15, show_spinner=False)
def get_json(backend_url: str, path: str):
    with httpx.Client(trust_env=False, timeout=15, headers=api_headers()) as client:
        response = client.get(backend_url + path)
        response.raise_for_status()
        return response.json()


def post_json(backend_url: str, path: str, payload: dict, timeout: int = 180) -> dict:
    response = httpx.post(
        backend_url + path,
        json=payload,
        timeout=timeout,
        trust_env=False,
        headers=api_headers(),
    )
    response.raise_for_status()
    return response.json()


def wait_job(backend_url: str, job_id: str, timeout: int = 600, interval: float = 1.5) -> dict:
    """Poll GET /api/v1/jobs/{id} until terminal state. Bypasses Streamlit cache."""
    deadline = time.monotonic() + timeout
    with httpx.Client(trust_env=False, timeout=30, headers=api_headers()) as client:
        while time.monotonic() < deadline:
            response = client.get(f"{backend_url}/api/v1/jobs/{job_id}")
            response.raise_for_status()
            job = response.json()
            if job["status"] in {"succeeded", "failed"}:
                return job
            time.sleep(interval)
    raise TimeoutError("异步任务等待超时")


class JobFailed(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def run_job(backend_url: str, path: str, payload: dict, timeout: int = 600) -> dict:
    """Submit async job (202) and wait for result payload."""
    accepted = post_json(backend_url, path, payload, timeout=30)
    job = wait_job(backend_url, accepted["job_id"], timeout=timeout)
    if job["status"] == "failed":
        error = job.get("error") or {}
        raise JobFailed(error.get("code") or "job_failed", error.get("message") or "任务失败")
    return job["result"]


def request_error(exc: Exception, fallback: str) -> None:
    message = fallback
    if isinstance(exc, JobFailed):
        message = exc.message or fallback
    elif isinstance(exc, TimeoutError):
        message = "任务等待超时，请稍后在历史记录中查看，或检查后端状态。"
    elif isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code == 422:
            message = "输入条件未通过检查，请核对必填项、年份或数值范围。"
        else:
            try:
                message = exc.response.json().get("error", {}).get("message") or fallback
            except (ValueError, AttributeError):
                pass
    st.error(message)


def document_label(item: dict) -> str:
    authors = item.get("authors") or []
    author = authors[0] + (" 等" if len(authors) > 1 else "") if authors else "作者待补充"
    engine = "MinerU" if item.get("parser_engine") == "mineru" else "PyMuPDF"
    version = str(item["document_id"])[:6]
    return f"{author} · {item['title']} 〔{engine} · {version}〕"


def recent_documents(backend_url: str, selected: str | None = None) -> list[dict]:
    documents = get_json(backend_url, "/api/v1/documents?limit=10")[:10]
    if selected and selected not in {item["document_id"] for item in documents}:
        try:
            current = get_json(backend_url, f"/api/v1/documents/{selected}")
            if not current.get("deleted_at"):
                # Keep a paper opened from the full catalog selected without growing the list.
                documents = documents[:9] + [{"has_experiments": False, **current}]
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
    return documents


def browse_documents_button(key: str = "browse_documents") -> None:
    st.button(
        "查看更多 · 全部已解析论文",
        key=key,
        icon=":material/library_books:",
        on_click=go_to,
        args=("全部论文",),
    )


def research_context(backend_url: str) -> dict | None:
    pending = st.session_state.pop("pending_document_id", None)
    if pending:
        st.session_state.active_document_id = pending
        get_json.clear()
    existing = st.session_state.get("document", {}).get("document_id")
    active = st.session_state.get("active_document_id", existing)
    try:
        documents = recent_documents(backend_url, active)
    except (httpx.HTTPError, ValueError):
        st.caption("暂时无法读取文献列表；可稍后重试，或前往论文解析上传文献。")
        return st.session_state.get("document")
    lookup = {item["document_id"]: item for item in documents}
    if "active_document_id" not in st.session_state:
        st.session_state.active_document_id = existing if existing in lookup else None
    if st.session_state.active_document_id not in lookup:
        st.session_state.active_document_id = None
    with st.container(key="research_context"):
        chosen = st.selectbox(
            "当前研究文献",
            [None, *lookup],
            key="active_document_id",
            persist_state="session",
            placeholder="选择已解析的文献，或保持不限文献",
            format_func=lambda value: (
                "选择已解析的文献，或保持不限文献"
                if value is None
                else document_label(lookup[value])
            ),
            help="按作者与标题选择文献，末尾标识用于区分解析版本。可在论文解析中编辑论文信息。",
        )
        if chosen:
            item = lookup[chosen]
            st.caption(
                f"{item['filename']} · "
                f"{item['page_count']} 页 · "
                f"{'已有实验记录' if item['has_experiments'] else '可提取实验记录'}"
            )
        st.caption("最近解析的论文，最多展示 10 条；从全部论文打开的当前文献会保留在列表中。")
        browse_documents_button()
    if not chosen:
        st.session_state.pop("document", None)
        return None
    try:
        document = get_json(backend_url, f"/api/v1/documents/{chosen}")
        st.session_state.document = document
        return document
    except (httpx.HTTPError, ValueError) as exc:
        st.session_state.pop("document", None)
        request_error(exc, "所选文献暂时无法读取，请重新选择或检查后端。")
        return None


def activate_document(document: dict) -> None:
    st.session_state.document = document
    st.session_state.pending_document_id = document["document_id"]
    st.rerun()


def safe_link(label: str, url: str | None, *, key: str | None = None) -> None:
    try:
        valid = url and urlsplit(url).scheme in {"https", "http"} and urlsplit(url).netloc
    except ValueError:
        valid = False
    if valid:
        st.link_button(label, url, key=key, icon=":material/open_in_new:")


@st.dialog("原文与来源", width="large")
def evidence_dialog(title: str, text: str, location: str, url: str | None = None) -> None:
    st.subheader(title)
    st.caption(location)
    st.text(text)
    safe_link("打开文献来源", url)
    st.caption("引文用于定位证据；原文匹配不能替代科研人工审核。")
    if st.button("返回继续阅读", type="primary", width="stretch"):
        st.rerun()


def number(value, unit: str = "") -> str:
    return "未提供" if value is None else f"{value:g}{' ' + unit if unit else ''}"
