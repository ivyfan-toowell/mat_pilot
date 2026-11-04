"""Live two-expert workflow, independent review, checkpoint and saved-result UI."""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from uuid import UUID

import httpx
from playwright.sync_api import expect, sync_playwright

from app.agents.collaboration import validate_quantities
from app.agents.research import validate_agent_claims
from app.core.config import PROJECT_ROOT
from app.schemas.agent import AgentDraft, AgentResult


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id", type=UUID, help="Reuse a completed live run for UI verification"
    )
    args = parser.parse_args()
    folder = PROJECT_ROOT / "data/acceptance/collaboration"
    folder.mkdir(parents=True, exist_ok=True)
    request = {
        "question": "请查询 Materials Project 中化学式严格为 TiO2 的候选材料，计算带隙 0–10 eV，"
        "energy above hull 不超过 0.05 eV/atom，最多 3 条。检索所选论文并读取实验记录，给出 "
        "TiO2-24 与 TiO2-48 的实验带隙，区分计算与实验数据并说明可比较性局限。"
        "仅陈述工具能证明的事实，不推测晶相、合成路径、误差范围或全文未报告的内容。",
        "document_id": "377d0571-bae4-4667-9caa-9ba49e059dd8",
        "required_tools": ["search_materials", "search_papers", "read_experiments"],
        "workflow_mode": "collaborative",
        "max_steps": 4,
        "max_model_calls": 10,
        "time_budget_seconds": 300,
    }
    with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=600) as client:
        response = (
            client.get(f"/api/agent/runs/{args.run_id}")
            if args.run_id
            else client.post("/api/agent/run", json=request)
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Collaborative task failed HTTP {response.status_code}: {response.text}"
            )
        result = response.json()
        parsed_result = AgentResult.model_validate(result)
        validate_agent_claims(AgentDraft(claims=parsed_result.claims), parsed_result.tools)
        validate_quantities(AgentDraft(claims=parsed_result.claims))
        trace = result["collaboration"]
        if result["workflow_mode"] != "collaborative" or result["status"] != "answered":
            raise RuntimeError("Collaborative task did not answer")
        successful = {tool["name"] for tool in result["tools"] if tool["status"] == "ok"}
        if not set(request["required_tools"]).issubset(successful):
            raise RuntimeError("Required expert sources not completed")
        if not trace["reviews"] or not all(
            check["supported"] for check in trace["reviews"][-1]["checks"]
        ):
            raise RuntimeError("No successful independent claim review")
        if not {"materials", "literature", "reviewer"}.issubset(
            {role["role"] for role in trace["roles"]}
        ):
            raise RuntimeError("Expert/reviewer role execution missing")
        if not {"3.42", "3.09"}.issubset(set(re.findall(r"\d+\.\d+", result["answer"]))):
            raise RuntimeError("Experimental gap answer mismatch")
        material_record = next(
            tool
            for tool in result["tools"]
            if tool["name"] == "search_materials" and tool["status"] == "ok"
        )
        batch = json.loads(material_record["content"])
        query = batch["query"]
        if (
            query["formula"] != "TiO2"
            or query["band_gap_min"] != 0
            or query["band_gap_max"] != 10
            or query["energy_above_hull_max"] != 0.05
            or query["limit"] != 3
            or len(batch["materials"]) != 3
            or any(item["formula"] != "TiO2" for item in batch["materials"])
        ):
            raise RuntimeError("Expert did not preserve the requested material constraints")
        if client.get(f"/api/agent/runs/{result['run_id']}").raise_for_status().json() != result:
            raise RuntimeError("Saved result differs from response")
        checkpoint = (
            client.get(f"/api/agent/runs/{result['run_id']}/checkpoint").raise_for_status().json()
        )
        if (
            checkpoint["phase"] != "completed"
            or checkpoint["model_calls"] > request["max_model_calls"]
        ):
            raise RuntimeError("Checkpoint or budget mismatch")
        # Save the live result before UI inspection so a harness failure cannot lose it.
        (folder / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "workflow": "PASS",
                "run_id": result["run_id"],
                "model_calls": trace["model_calls"],
                "execution": trace["execution_mode"],
            }
        ),
        flush=True,
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto("http://127.0.0.1:8501")
            page.get_by_text("科研助手", exact=True).first.click()
            page.get_by_text("读取历史任务", exact=True).click()
            page.get_by_label("历史任务 ID", exact=True).fill(result["run_id"])
            page.get_by_label("历史任务 ID", exact=True).press("Enter")
            page.get_by_role("button", name="读取已保存任务", exact=True).click()
            expect(page.locator(".st-key-agent_answer")).to_contain_text("3.42", timeout=30000)
            page.get_by_text("协作计划、角色执行与 Reviewer 复核", exact=True).click()
            page.screenshot(path=str(folder / "reviewed-task.png"), full_page=True)
            if errors:
                raise RuntimeError("JavaScript error in collaboration UI")
            report = {
                "verified_at": datetime.now(UTC).isoformat(),
                "request": request,
                "result": result,
                "checkpoint": checkpoint,
                "page_errors": errors,
                "limitations": [
                    "模型复核不能代替科研人员审核。",
                    "阶段状态保存不等于跨进程自动恢复。",
                ],
            }
            (folder / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (folder / "failure.png").unlink(missing_ok=True)
            print("Saved-result UI and collaboration acceptance PASS", flush=True)
        except Exception:
            page.screenshot(path=str(folder / "failure.png"), full_page=True)
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    main()
