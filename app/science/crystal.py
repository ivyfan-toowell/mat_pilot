"""根据真实 pymatgen 晶体结构计算晶格与几何指标。"""

from datetime import UTC, datetime

from pymatgen.core import Structure

from app.schemas.material import CrystalStructureResult


def describe_structure(
    material_id: str, structure: Structure, version: str | None
) -> CrystalStructureResult:
    return CrystalStructureResult(
        material_id=material_id,
        formula=structure.composition.reduced_formula,
        site_count=len(structure),
        lattice_lengths=structure.lattice.abc,
        lattice_angles=structure.lattice.angles,
        volume=structure.volume,
        structure=structure.as_dict(),
        source_url=f"https://materialsproject.org/materials/{material_id}",
        data_version=version,
        retrieved_at=datetime.now(UTC),
    )
