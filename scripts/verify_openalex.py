"""Live OpenAlex HTTP, snapshot and Edge/agent acceptance; remote calls incur usage."""

import json
import re
import sys
from datetime import UTC, datetime

import httpx
from playwright.sync_api import expect, sync_playwright

from app.core.config import PROJECT_ROOT, get_settings

DOI = "10.3390/nano10030546"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    folder = PROJECT_ROOT / "data/acceptance/openalex"
    folder.mkdir(parents=True, exist_ok=True)
    key = get_settings().openalex_api_key
    if not key:
        raise RuntimeError("OpenAlex key is not configured")
    records = {}
    with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=100) as client:
        for name, query in {
            "doi": {
                "query": DOI,
                "limit": 3,
                "open_access_only": True,
                "year_from": 2020,
                "year_to": 2020,
            },
            "keywords": {
                "query": "TiO2 oxygen vacancies photocatalysis",
                "limit": 3,
                "open_access_only": True,
                "year_from": 2020,
                "year_to": 2026,
                "sort": "citations",
            },
        }.items():
            response = client.post("/api/literature/search", json=query).raise_for_status()
            result = response.json()
            if not result["papers"] or not result["metadata_only"]:
                raise RuntimeError("Live query did not return metadata")
            if name == "doi" and result["papers"][0]["doi"] != DOI:
                raise RuntimeError("Live DOI result mismatch")
            readback = (
                client.get(f"/api/literature/queries/{result['query_id']}")
                .raise_for_status()
                .json()
            )
            if readback != result:
                raise RuntimeError("Metadata snapshot readback mismatch")
            if key.get_secret_value() in response.text:
                raise RuntimeError("Credential present in metadata response")
            records[name] = result
            print(f"HTTP {name} and snapshot PASS", flush=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.set_default_timeout(30000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto("http://127.0.0.1:8501")
            page.get_by_text("论文发现", exact=True).first.click()
            page.get_by_label("论文关键词或 DOI", exact=True).fill(DOI)
            page.get_by_role("button", name="检索在线论文", exact=True).click()
            results = page.locator(".st-key-literature_results")
            expect(results).to_contain_text("论文结果 · 1 条", timeout=100000)
            expect(results).to_contain_text(DOI)
            expect(page.get_by_role("link", name="打开 DOI", exact=True)).to_have_attribute(
                "href", f"https://doi.org/{DOI}"
            )
            page.screenshot(path=str(folder / "discovery.png"), full_page=True)
            print("Browser paper discovery PASS", flush=True)

            page.get_by_text("科研助手", exact=True).first.click()
            page.get_by_role("combobox", name="本任务必须完成的资料来源（可选）").click()
            page.get_by_role("option", name="在线论文元数据", exact=True).click()
            page.get_by_label("科研问题", exact=True).fill(
                f"请仅使用 OpenAlex 查询 DOI {DOI}，给出这篇论文的标题、作者、发表年份和 DOI。"
                "只需要元数据，不分析实验结果，也不要检索本地全文或 Materials Project。"
            )
            page.get_by_role("button", name="执行科研任务", exact=True).click()
            answer = page.locator(".st-key-agent_answer")
            expect(answer).to_contain_text(DOI, timeout=240000)
            # Streamlit calls FastAPI from Python; browser traffic only sees its WebSocket.
            task_label = page.get_by_text(re.compile(r"任务 ID："))
            run_id = re.search(r"[a-f0-9-]{36}", task_label.inner_text())[0]
            with httpx.Client(
                base_url="http://127.0.0.1:8000", trust_env=False, timeout=10
            ) as client:
                agent = client.get(f"/api/agent/runs/{run_id}").raise_for_status().json()
            successful = {tool["name"] for tool in agent["tools"] if tool["status"] == "ok"}
            if (
                successful != {"search_academic_papers"}
                or agent["status"] != "answered"
                or not agent["claims"]
            ):
                raise RuntimeError("Metadata Agent did not complete its scoped task")
            expect(answer).to_contain_text(DOI, timeout=30000)
            expect(answer).to_contain_text("2020")
            page.screenshot(path=str(folder / "agent.png"), full_page=True)
            if errors:
                raise RuntimeError("Browser JavaScript error")
            report = {
                "verified_at": datetime.now(UTC).isoformat(),
                "http": records,
                "agent": agent,
                "page_errors": errors,
                "scope": "Bibliographic metadata discovery only; no full text downloaded "
                "or scientific claims verified.",
            }
            payload = json.dumps(report, ensure_ascii=False, indent=2)
            if key.get_secret_value() in payload:
                raise RuntimeError("Credential present in acceptance artifact")
            (folder / "report.json").write_text(payload, encoding="utf-8")
            print(
                json.dumps(
                    {
                        "result": "PASS",
                        "agent_run_id": agent["run_id"],
                        "report": str(folder / "report.json"),
                    },
                    ensure_ascii=False,
                )
            )
        except Exception:
            page.screenshot(path=str(folder / "failure.png"), full_page=True)
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    main()
