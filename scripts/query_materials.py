"""Run a bounded real query: uv run python -m scripts.query_materials."""

import argparse
import sys

from app.core.config import LOCAL_TENANT_ID, get_settings, tenant_data_dir
from app.core.errors import ServiceError
from app.core.logging import configure_logging
from app.schemas.material import MaterialQuery
from app.science.materials_project import MaterialsProjectService
from app.services.material_service import QueryStore, export_csv


def main() -> int:
    # PowerShell tool output is decoded as UTF-8, including stderr in pipes.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Query real Materials Project data")
    parser.add_argument("--formula", default=None)
    parser.add_argument("--elements", nargs="*", default=["O"])
    parser.add_argument("--band-gap-min", type=float, default=1.5)
    parser.add_argument("--band-gap-max", type=float, default=3.0)
    parser.add_argument("--hull-max", type=float, default=0.05)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level)
    try:
        query = MaterialQuery(
            formula=args.formula,
            elements=args.elements,
            band_gap_min=args.band_gap_min,
            band_gap_max=args.band_gap_max,
            energy_above_hull_max=args.hull_max,
            limit=args.limit,
        )
        result = MaterialsProjectService(settings).search(query)
        root = tenant_data_dir(settings, LOCAL_TENANT_ID)
        QueryStore(root).save(result)
        csv_path = root / "material_queries" / f"{result.query_id}.csv"
        csv_path.write_text(export_csv(result), encoding="utf-8-sig")
    except (ServiceError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(result.model_dump_json(indent=2))
    print(f"CSV saved: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
