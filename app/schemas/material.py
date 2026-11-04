"""定义材料筛选条件、计算属性、结构及查询结果的数据结构。"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.science.composition import normalize_elements, normalize_formula

# Live MP responses also use alphanumeric identifiers.
MATERIAL_ID_PATTERN = r"^mp-[a-z0-9]+$"

SCIENTIFIC_CAVEAT = (
    "以下为 Materials Project 计算数据，不是实验测量值。"
    "计算带隙与实验带隙可能不同；Energy Above Hull 仅用于初步热力学筛选，"
    "不能据此判定合成可行性、光学性能或实际器件性能。"
)


class MaterialQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    elements: list[str] = Field(default_factory=lambda: ["O"], max_length=20)
    formula: str | None = Field(default=None, max_length=100)
    band_gap_min: float = Field(default=1.5, ge=0, description="eV")
    band_gap_max: float = Field(default=3.0, ge=0, description="eV")
    energy_above_hull_max: float = Field(default=0.05, ge=0, description="eV/atom")
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("elements")
    @classmethod
    def validate_elements(cls, value: list[str]) -> list[str]:
        return normalize_elements(value)

    @field_validator("formula")
    @classmethod
    def validate_formula(cls, value: str | None) -> str | None:
        return normalize_formula(value) if value is not None else None

    @model_validator(mode="after")
    def validate_bounds(self) -> "MaterialQuery":
        if self.band_gap_min > self.band_gap_max:
            raise ValueError("带隙下限不能超过上限。")
        return self


class Material(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    material_id: str = Field(pattern=MATERIAL_ID_PATTERN)
    formula: str
    band_gap: float | None = Field(default=None, ge=0, description="eV")
    formation_energy_per_atom: float | None = Field(default=None, description="eV/atom")
    energy_above_hull: float | None = Field(default=None, ge=0, description="eV/atom")
    is_gap_direct: bool | None = None
    is_stable: bool | None = None
    crystal_system: str | None = None
    space_group: str | None = None
    source_database: Literal["Materials Project"] = "Materials Project"
    data_kind: Literal["computed"] = "computed"
    source_url: str
    data_version: str | None = None
    retrieved_at: datetime
    calculation_provenance: list[dict[str, Any]] = Field(default_factory=list)


class MaterialSearchResult(BaseModel):
    query_id: UUID
    query: MaterialQuery
    materials: list[Material]
    retrieved_at: datetime
    # The bounded first batch is not a global ranking or an exhaustive search.
    possibly_truncated: bool
    units: dict[str, str] = Field(
        default_factory=lambda: {
            "band_gap": "eV",
            "formation_energy_per_atom": "eV/atom",
            "energy_above_hull": "eV/atom",
        }
    )
    warnings: list[str] = Field(default_factory=lambda: [SCIENTIFIC_CAVEAT])


class CrystalStructureResult(BaseModel):
    material_id: str = Field(pattern=MATERIAL_ID_PATTERN)
    formula: str
    site_count: int
    lattice_lengths: tuple[float, float, float]
    lattice_angles: tuple[float, float, float]
    volume: float
    structure: dict[str, Any]
    source_url: str
    data_kind: Literal["computed"] = "computed"
    data_version: str | None = None
    retrieved_at: datetime
    units: dict[str, str] = Field(
        default_factory=lambda: {
            "lattice_lengths": "angstrom",
            "lattice_angles": "degree",
            "volume": "angstrom^3",
        }
    )
