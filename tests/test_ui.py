"""验证真实 Streamlit 工作区导航、输入保留及浏览页面不触发付费请求。"""

from pathlib import Path

import httpx
from streamlit.testing.v1 import AppTest

from ui import shared


def test_workspace_navigation_preserves_question_without_paid_calls(monkeypatch):
    monkeypatch.setattr(shared, "service_status", lambda _: {"status": "ready"})
    monkeypatch.setattr(shared, "get_json", lambda *_: [])

    def unexpected_post(*args, **kwargs):
        raise AssertionError("浏览工作区不得触发模型或材料查询")

    monkeypatch.setattr(httpx, "post", unexpected_post)
    page = AppTest.from_file(str(Path(__file__).parents[1] / "ui" / "app.py")).run()
    assert not page.exception
    page.button(key="nav_knowledge").click().run()
    assert not page.exception
    page.text_area(key="knowledge_question").input("跨页面保留的科研问题").run()
    page.button(key="nav_materials").click().run()
    page.button(key="nav_knowledge").click().run()
    assert not page.exception
    assert page.text_area(key="knowledge_question").value == "跨页面保留的科研问题"
    for key in ("nav_discovery", "nav_documents", "nav_assistant"):
        page.button(key=key).click().run()
        assert not page.exception


def test_material_results_keep_missing_values_and_render_without_query(monkeypatch):
    monkeypatch.setattr(shared, "service_status", lambda _: {"status": "ready"})
    monkeypatch.setattr("ui.material_page.query_csv", lambda *_: b"fixture-only")
    page = AppTest.from_file(str(Path(__file__).parents[1] / "ui" / "app.py")).run()
    page.session_state["material_result"] = {
        "query_id": "fixture-only",
        "retrieved_at": "fixture-only",
        "warnings": [],
        "materials": [
            {
                "material_id": "mp-fixture",
                "formula": "TiO2",
                "band_gap": None,
                "energy_above_hull": None,
                "crystal_system": None,
            }
        ],
    }
    page.run()
    assert not page.exception
    assert page.dataframe[0].value["计算带隙（eV）"].isna().all()
    assert page.dataframe[0].value["凸包能差（eV/atom）"].isna().all()
