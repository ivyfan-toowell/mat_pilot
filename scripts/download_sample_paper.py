"""Download one explicitly CC BY 4.0 paper for parser acceptance."""

import hashlib
import json
import sys
from datetime import UTC, datetime

import httpx

from app.core.config import get_settings


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    urls = [
        "https://pmc.ncbi.nlm.nih.gov/articles/PMC7153365/pdf/nanomaterials-10-00546.pdf",
        "https://europepmc.org/articles/PMC7153365?pdf=render",
        "https://mdpi-res.com/d_attachment/nanomaterials/nanomaterials-10-00546/"
        "article_deploy/nanomaterials-10-00546.pdf",
    ]
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for url in urls:
            try:
                response = client.get(url)
                if response.status_code != 200 or not response.content.startswith(b"%PDF-"):
                    print(f"PDF candidate unavailable: HTTP {response.status_code}")
                    continue
                if len(response.content) > 30 * 1024 * 1024:
                    raise ValueError("sample exceeds file size limit")
                folder = get_settings().data_dir / "sample_papers"
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "PMC7153365.pdf").write_bytes(response.content)
                metadata = {
                    "title": "Effects of Particle Size on the Structure and Photocatalytic "
                    "Performance by Alkali-Treated TiO2",
                    "doi": "10.3390/nano10030546",
                    "pmcid": "PMC7153365",
                    "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7153365/",
                    "license": "CC BY 4.0",
                    "license_url": "https://creativecommons.org/licenses/by/4.0/",
                    "download_url": url,
                    "downloaded_at": datetime.now(UTC).isoformat(),
                    "sha256": hashlib.sha256(response.content).hexdigest(),
                    "bytes": len(response.content),
                }
                (folder / "PMC7153365.source.json").write_text(
                    json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(json.dumps(metadata, ensure_ascii=False, indent=2))
                return 0
            except (httpx.HTTPError, ValueError) as exc:
                print(f"PDF candidate failed: {type(exc).__name__}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
