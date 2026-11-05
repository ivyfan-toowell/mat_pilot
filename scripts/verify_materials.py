"""Verify the materials API with an existing live query and two real follow-up calls."""

import argparse
import json
import sys
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from pymatgen.core import Structure

from app.core.config import PROJECT_ROOT, get_settings
from app.main import app
from app.services.material_service import QueryStore


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-id", type=UUID, required=True)
    args = parser.parse_args()
    settings = get_settings()
    from app.core.config import LOCAL_TENANT_ID, tenant_data_dir

    snapshot = QueryStore(tenant_data_dir(settings, LOCAL_TENANT_ID)).load(args.query_id)
    material_id = snapshot.materials[0].material_id
    report = {"checked_at": datetime.now(UTC).isoformat(), "query_id": str(args.query_id)}
    try:
        with TestClient(app) as client:
            responses = {
                "health": client.get("/health"),
                "saved_query": client.get(f"/api/v1/materials/queries/{args.query_id}"),
                "csv": client.get(f"/api/v1/materials/queries/{args.query_id}/csv"),
                "details": client.get(f"/api/v1/materials/{material_id}"),
                "structure": client.get(f"/api/v1/materials/{material_id}/structure"),
            }
            report["http_status"] = {
                name: response.status_code for name, response in responses.items()
            }
            for response in responses.values():
                response.raise_for_status()
            structure_result = responses["structure"].json()
            crystal = Structure.from_dict(structure_result["structure"])
            if responses["details"].json()["material_id"] != material_id:
                raise ValueError("unexpected detail ID")
            if material_id not in responses["csv"].text or crystal.volume <= 0:
                raise ValueError("invalid export or structure")
            report["material_id"] = material_id
            report["site_count"] = len(crystal)
            report["volume_angstrom3"] = crystal.volume
        from streamlit.testing.v1 import AppTest

        page = AppTest.from_file(str(PROJECT_ROOT / "ui" / "app.py")).run(timeout=20)
        if page.exception:
            raise RuntimeError("Streamlit page initialization failed")
        report["streamlit_initial_page"] = "passed"
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
    destination = settings.data_dir / "acceptance"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "materials.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
