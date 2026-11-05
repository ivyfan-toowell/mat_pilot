"""Live HTTP and Edge UI acceptance against an already indexed real paper."""

import argparse
import json
import sys
from datetime import UTC, datetime
from uuid import UUID

import httpx
from playwright.sync_api import expect, sync_playwright

from app.core.config import PROJECT_ROOT


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", type=UUID, required=True)
    args = parser.parse_args()
    document_id = str(args.document_id)
    folder = PROJECT_ROOT / "data/acceptance/hybrid"
    folder.mkdir(parents=True, exist_ok=True)
    question = "TiO2-24 与 TiO2-48 的实验光学带隙分别是多少？"
    records = {}
    with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=120) as client:
        readiness = client.get("/health/ready").raise_for_status().json()
        for mode in ("dense", "sparse", "hybrid"):
            result = (
                client.post(
                    "/api/v1/knowledge/search",
                    json={"question": question, "document_id": document_id, "retrieval_mode": mode},
                )
                .raise_for_status()
                .json()
            )
            assert result["retrieval_mode"] == mode and result["hits"]
            assert all(hit["document_id"] == document_id for hit in result["hits"])
            if mode == "sparse":
                assert all(
                    hit["similarity"] is None and hit["sparse_score"] > 0 for hit in result["hits"]
                )
            if mode == "hybrid":
                assert all(hit["rrf_score"] > 0 for hit in result["hits"])
            records[mode] = result
        assert (
            client.post(
                "/api/v1/knowledge/search", json={"question": question, "retrieval_mode": "invalid"}
            ).status_code
            == 422
        )
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto("http://127.0.0.1:8501")
            page.get_by_text("文献知识库", exact=True).first.click()
            page.get_by_label("文献 ID（留空则检索整个知识库）", exact=True).fill(document_id)
            page.get_by_label("向论文提问", exact=True).fill(question)
            page.get_by_text("带引用回答", exact=True).click()
            page.get_by_role("combobox", name="检索策略").click()
            page.get_by_role("option", name="Hybrid 混合", exact=True).click()
            page.get_by_text("使用通义 Rerank 重排（额外模型调用）", exact=True).click()
            page.get_by_role("button", name="查询知识库", exact=True).click()
            answer = page.locator(".st-key-knowledge_answer")
            expect(answer).to_contain_text("3.42", timeout=120000)
            expect(answer).to_contain_text("3.09", timeout=120000)
            page.get_by_text("[1] 第", exact=False).first.click()
            expect(page.get_by_text("Rerank：", exact=False).first).to_be_visible()
            page.screenshot(path=str(folder / "knowledge.png"), full_page=True)
            if errors:
                raise RuntimeError("JavaScript errors in hybrid UI")
            report = {
                "verified_at": datetime.now(UTC).isoformat(),
                "document_id": document_id,
                "readiness": readiness,
                "http_search": records,
                "ui_strategy": "hybrid_rerank",
                "answer": answer.inner_text(),
                "page_errors": errors,
            }
            (folder / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(
                json.dumps(
                    {"result": "PASS", "report": str(folder / "report.json")}, ensure_ascii=False
                )
            )
        except Exception:
            page.screenshot(path=str(folder / "failure.png"), full_page=True)
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    main()
