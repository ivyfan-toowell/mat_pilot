"""Live browser workflow, real backends and models; outputs screenshots and a report."""

import json
import re
import sys
from datetime import UTC, datetime

from playwright.sync_api import expect, sync_playwright

from app.core.config import PROJECT_ROOT


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    output = PROJECT_ROOT / "data" / "acceptance" / "browser"
    output.mkdir(parents=True, exist_ok=True)
    stages = []
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_default_timeout(30000)
        try:
            page.goto("http://127.0.0.1:8501")
            page.get_by_label("化学式（可选）", exact=True).fill("TiO2")
            page.get_by_label("带隙下限（eV）", exact=True).fill("0")
            page.get_by_label("带隙上限（eV）", exact=True).fill("10")
            page.get_by_label("查询条数上限", exact=True).fill("3")
            page.get_by_role("button", name="查询真实材料").click()
            expect(page.get_by_text("候选材料 · 3 条", exact=True)).to_be_visible(timeout=180000)
            page.screenshot(path=str(output / "01-materials.png"), full_page=True)
            stages.append("live_material_query")
            print("Browser: real material query PASS", flush=True)

            page.get_by_text("论文解析", exact=True).click()
            page.locator('input[type="file"]').set_input_files(
                str(PROJECT_ROOT / "data/sample_papers/PMC7153365.pdf")
            )
            page.get_by_label("原文链接（可选）", exact=True).fill(
                "https://pmc.ncbi.nlm.nih.gov/articles/PMC7153365/"
            )
            page.get_by_label("文献许可（可选）", exact=True).fill("CC BY 4.0")
            page.get_by_role("button", name="解析论文", exact=True).click()
            document_label = page.get_by_text(re.compile(r"14 页 · 文献 ID："))
            expect(document_label).to_be_visible(timeout=120000)
            document_id = re.search(r"[a-f0-9-]{36}", document_label.inner_text())[0]
            page.get_by_role("button", name="提取实验带隙", exact=True).click()
            expect(page.get_by_role("button", name="下载实验记录与证据 JSON")).to_be_visible(
                timeout=120000
            )
            if page.get_by_text("未获得通过证据校验的实验记录。", exact=True).count():
                raise RuntimeError("Browser extraction yielded no accepted records")
            page.screenshot(path=str(output / "02-documents.png"), full_page=True)
            stages.append("pdf_upload_parse_extract")
            print("Browser: PDF upload, parse and extraction PASS", flush=True)

            page.get_by_text("文献知识库", exact=True).first.click()
            page.get_by_role("button", name="将文献加入知识库", exact=True).click()
            expect(page.get_by_text(re.compile(r"已索引 \d+ 个文档块"))).to_be_visible(
                timeout=180000
            )
            page.get_by_label("向论文提问", exact=True).fill(
                "TiO2-24 与 TiO2-48 的实验带隙各是多少？"
            )
            page.get_by_text("带引用回答", exact=True).click()
            page.get_by_role("button", name="查询知识库", exact=True).click()
            answer = page.locator(".st-key-knowledge_answer")
            expect(answer).to_contain_text("3.42", timeout=120000)
            expect(answer).to_contain_text("3.09", timeout=120000)
            page.screenshot(path=str(output / "03-knowledge.png"), full_page=True)
            stages.append("index_retrieve_answer")
            print("Browser: pgvector index and cited RAG answer PASS", flush=True)

            page.get_by_text("科研助手", exact=True).first.click()
            page.get_by_label("科研问题", exact=True).fill(
                "请检索所选论文并读取已提取实验记录，比较 TiO2-24 和 TiO2-48 的带隙并给出来源。"
            )
            page.get_by_role("button", name="执行科研任务", exact=True).click()
            expect(page.get_by_text(re.compile(r"任务 ID："))).to_be_visible(timeout=240000)
            if page.get_by_text("目前没有足够的工具证据支持回答。", exact=True).count():
                raise RuntimeError("Agent returned insufficient evidence")
            page.screenshot(path=str(output / "04-agent.png"), full_page=True)
            stages.append("research_agent")
            if errors:
                raise RuntimeError("Browser reported JavaScript errors")
            print("Browser: LangGraph research agent PASS", flush=True)
            report = {
                "verified_at": datetime.now(UTC).isoformat(),
                "browser": "Microsoft Edge headless",
                "document_id": document_id,
                "stages": stages,
                "page_errors": errors,
            }
            (output / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            page.screenshot(path=str(output / "failure.png"), full_page=True)
            (output / "failure.json").write_text(
                json.dumps(
                    {
                        "stages": stages,
                        "page_errors": errors,
                        "body": page.locator("body").inner_text(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    main()
