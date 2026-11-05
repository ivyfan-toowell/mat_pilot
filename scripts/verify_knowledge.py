"""Live HTTP acceptance against a real parsed paper, PostgreSQL, and DashScope."""

import argparse
import json
import sys
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app
from app.services.vector_store import VectorStore


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-id", type=UUID, required=True)
    args = parser.parse_args()
    question = (
        "What are the optical band gaps of TiO2-24 and TiO2-48 reported in Table 1 "
        "of this paper? Please cite the original evidence."
    )
    with TestClient(app) as client:
        indexed = client.post(f"/api/v1/knowledge/documents/{args.document_id}/index")
        if indexed.status_code != 200:
            raise RuntimeError(f"index failed: {indexed.status_code}, {indexed.text}")
        request = {"question": question, "document_id": str(args.document_id), "top_k": 8}
        searched = client.post("/api/v1/knowledge/search", json=request)
        if searched.status_code != 200 or not searched.json()["hits"]:
            raise RuntimeError("live search returned no evidence")
        answer = client.post("/api/v1/knowledge/answer", json=request)
        if answer.status_code != 200 or answer.json()["status"] != "answered":
            raise RuntimeError(f"live answer failed: {answer.status_code}, {answer.text}")
    settings = get_settings()
    with VectorStore(settings).connect() as connection:
        row = connection.execute(
            "SELECT count(*) AS count FROM mp_chunks WHERE document_id=%s", (args.document_id,)
        ).fetchone()
        if row["count"] != indexed.json()["chunks"]:
            raise RuntimeError("persisted chunk count mismatch")
    report = {
        "verified_at": datetime.now(UTC).isoformat(),
        "index": indexed.json(),
        "persisted_chunks": row["count"],
        "search": searched.json(),
        "answer": answer.json(),
        "scope": "single-paper live acceptance; not a retrieval benchmark",
    }
    folder = settings.data_dir / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "knowledge.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "chunks": row["count"],
                "hits": len(searched.json()["hits"]),
                "status": answer.json()["status"],
                "answer": answer.json()["answer"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
