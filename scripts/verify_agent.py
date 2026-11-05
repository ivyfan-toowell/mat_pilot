"""Live MVP research task requiring both MP computation and paper evidence."""

import json
import sys

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agent/run",
            json={
                "question": "请查询 Materials Project 中 TiO2 的候选材料，带隙范围 0–10 eV，"
                "energy above hull 不超过 0.05 eV/atom，最多 3 条。"
                "再检索所选论文，给出 TiO2-24 与 TiO2-48 的实验带隙，"
                "区分计算数据和实验估计，并说明比较局限。必须调用材料查询及文献检索。",
                "document_id": "377d0571-bae4-4667-9caa-9ba49e059dd8",
                "max_steps": 6,
                "required_tools": ["search_materials", "search_papers"],
            },
        )
        if response.status_code != 200:
            raise RuntimeError(f"Agent failed: {response.status_code}, {response.text}")
        result = response.json()
        names = {tool["name"] for tool in result["tools"] if tool["status"] == "ok"}
        if not {"search_materials", "search_papers"}.issubset(names) or not result["claims"]:
            raise RuntimeError("Agent did not complete the required tools and cited answer")
        material_tool = next(
            tool
            for tool in result["tools"]
            if tool["name"] == "search_materials" and tool["status"] == "ok"
        )
        query_id = json.loads(material_tool["content"])["query_id"]
        batch = json.loads(material_tool["content"])
        if batch["query"]["formula"] != "TiO2" or any(
            material["formula"] != "TiO2" for material in batch["materials"]
        ):
            raise RuntimeError("Agent failed to preserve the requested TiO2 formula constraint")
        comparison = client.post("/api/v1/materials/compare", json={"query_id": query_id})
        if comparison.status_code != 200 or len(comparison.json()["materials"]) != 3:
            raise RuntimeError("Material comparison did not preserve the real candidate batch")
        if client.get(f"/api/v1/agent/runs/{result['run_id']}").json() != result:
            raise RuntimeError("Saved agent trace differs from the HTTP response")
    folder = get_settings().data_dir / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "agent.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "run_id": result["run_id"],
                "status": result["status"],
                "tools": list(names),
                "answer": result["answer"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
