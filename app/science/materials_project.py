"""调用 Materials Project 查询材料计算属性、来源和晶体结构。"""

import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ServiceError
from app.schemas.material import (
    MATERIAL_ID_PATTERN,
    CrystalStructureResult,
    Material,
    MaterialQuery,
    MaterialSearchResult,
)
from app.science.crystal import describe_structure

logger = logging.getLogger(__name__)
SUMMARY_FIELDS = [
    "material_id",
    "formula_pretty",
    "band_gap",
    "formation_energy_per_atom",
    "energy_above_hull",
    "is_gap_direct",
    "is_stable",
    "symmetry",
    "origins",
]


def create_mp_client(settings: Settings) -> Any:
    if not settings.mp_api_key:
        raise ServiceError("mp_not_configured", "请在本地 .env 中设置 MP_API_KEY。", 503)
    from mp_api.client import MPRester

    client = MPRester(
        api_key=settings.mp_api_key.get_secret_value(),
        timeout=settings.mp_timeout_seconds,
        use_document_model=False,
        mute_progress_bars=True,
    )
    # New SDK sub-resters may be LazyImport proxies with immutable attributes.
    # Configure supported options on MPRester instead of mutating those proxies.
    return client


class MaterialsProjectService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _check_id(material_id: str) -> None:
        if re.fullmatch(MATERIAL_ID_PATTERN, material_id) is None:
            raise ServiceError(
                "invalid_material_id", "MP-ID 应以 mp- 开头，后接数字或小写字母。", 422
            )

    def get_details(self, material_id: str) -> Material:
        self._check_id(material_id)
        try:
            with create_mp_client(self.settings) as client:
                records = client.materials.summary.search(
                    material_ids=[material_id],
                    fields=SUMMARY_FIELDS,
                    all_fields=False,
                    num_chunks=1,
                    chunk_size=1,
                )
                if not records:
                    raise ServiceError("material_not_found", "未找到该材料。", 404)
                return self._normalize(records[0], self._get_version(client), datetime.now(UTC))
        except ServiceError:
            raise
        except Exception as exc:
            logger.warning("MP details failed type=%s", type(exc).__name__)
            raise ServiceError("mp_query_failed", "Materials Project 材料详情查询失败。") from exc

    def get_structure(self, material_id: str) -> CrystalStructureResult:
        self._check_id(material_id)
        try:
            with create_mp_client(self.settings) as client:
                structure = client.get_structure_by_material_id(material_id)
                if structure is None:
                    raise ServiceError("structure_not_found", "未找到该材料的晶体结构。", 404)
                return describe_structure(material_id, structure, self._get_version(client))
        except ServiceError:
            raise
        except Exception as exc:
            logger.warning("MP structure failed type=%s", type(exc).__name__)
            raise ServiceError("mp_query_failed", "Materials Project 晶体结构查询失败。") from exc

    def search(self, query: MaterialQuery) -> MaterialSearchResult:
        try:
            with create_mp_client(self.settings) as client:
                records = client.materials.summary.search(
                    elements=query.elements or None,
                    formula=query.formula,
                    band_gap=(query.band_gap_min, query.band_gap_max),
                    energy_above_hull=(0, query.energy_above_hull_max),
                    deprecated=False,
                    num_chunks=1,
                    chunk_size=query.limit,
                    all_fields=False,
                    fields=SUMMARY_FIELDS,
                )
                version = self._get_version(client)
            retrieved_at = datetime.now(UTC)
            materials = [self._normalize(record, version, retrieved_at) for record in records]
            result = MaterialSearchResult(
                query_id=uuid4(),
                query=query,
                materials=materials,
                retrieved_at=retrieved_at,
                possibly_truncated=len(records) >= query.limit,
            )
            if result.possibly_truncated:
                result.warnings.append("达到查询上限；这是一批候选材料，不是全库排序结果。")
            logger.info("MP query completed query_id=%s count=%d", result.query_id, len(materials))
            return result
        except ServiceError:
            raise
        except ValidationError as exc:
            raise ServiceError("mp_invalid_data", "材料数据字段校验失败，未保存该批结果。") from exc
        except Exception as exc:
            # Provider exception text may contain request headers; do not expose it.
            logger.warning("MP query failed type=%s", type(exc).__name__)
            raise ServiceError(
                "mp_query_failed", "Materials Project 查询失败，请检查密钥、网络或服务配额。"
            ) from exc

    @staticmethod
    def _get_version(client: Any) -> str | None:
        try:
            version = client.db_version
            return str(version) if version else None
        except Exception:
            logger.warning("MP database version unavailable; preserving null version")
            return None

    @staticmethod
    def _normalize(record: dict[str, Any], version: str | None, at: datetime) -> Material:
        symmetry = record.get("symmetry") or {}
        material_id = str(record["material_id"])
        return Material(
            material_id=material_id,
            formula=record["formula_pretty"],
            band_gap=record.get("band_gap"),
            formation_energy_per_atom=record.get("formation_energy_per_atom"),
            energy_above_hull=record.get("energy_above_hull"),
            is_gap_direct=record.get("is_gap_direct"),
            is_stable=record.get("is_stable"),
            crystal_system=symmetry.get("crystal_system"),
            space_group=symmetry.get("symbol"),
            source_url=f"https://materialsproject.org/materials/{material_id}",
            data_version=version,
            retrieved_at=at,
            calculation_provenance=record.get("origins") or [],
        )
