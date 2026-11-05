"""Offline contract tests use explicit synthetic fixtures, never product data."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from app.core.config import Settings, get_settings
from app.core.errors import ServiceError
from app.main import app
from app.schemas.material import MaterialQuery
from app.science.composition import normalize_formula
from app.science.materials_project import MaterialsProjectService
from app.services.material_service import QueryStore, export_csv


@pytest.fixture
def settings(workspace_dir):
    return Settings(_env_file=None, mp_api_key=SecretStr("test-only-key"), data_dir=workspace_dir)


@pytest.fixture
def mp_client(monkeypatch):
    client = MagicMock()
    client.materials.summary.search.return_value = [
        {
            "material_id": "mp-999999999",
            "formula_pretty": "TiO2",
            "band_gap": 2.0,
            "formation_energy_per_atom": -1.0,
            "energy_above_hull": 0.01,
            "is_gap_direct": False,
            "is_stable": False,
            "symmetry": {"crystal_system": "Tetragonal", "symbol": "P4_2/mnm"},
            "origins": [{"name": "band_gap", "task_id": "mp-999999998"}],
        }
    ]
    client.db_version = "test-version"
    context = MagicMock()
    context.__enter__.return_value = client
    monkeypatch.setattr("app.science.materials_project.create_mp_client", lambda _: context)
    return client


def test_subscript_formula():
    assert normalize_formula("TiO₂") == "TiO2"


@pytest.mark.parametrize("formula", ["", "Xx2O", "Ti0O0"])
def test_invalid_formula(formula):
    with pytest.raises(ValueError):
        normalize_formula(formula)


@pytest.mark.parametrize(
    "params",
    [
        {"band_gap_min": 4, "band_gap_max": 2},
        {"band_gap_min": -1},
        {"energy_above_hull_max": -0.1},
        {"limit": 101},
        {"limit": 0},
        {"band_gap_max": float("nan")},
        {"band_gap_max": float("inf")},
        {"elements": ["Xx"]},
        {"formula": "not a formula"},
        {"unknown": True},
    ],
)
def test_invalid_query(params):
    with pytest.raises(ValidationError):
        MaterialQuery(**params)


def test_bounded_query_and_provenance(settings, mp_client):
    query = MaterialQuery(elements=["O", "O"], formula="TiO₂", limit=1)
    result = MaterialsProjectService(settings).search(query)
    call = mp_client.materials.summary.search.call_args.kwargs
    assert call["elements"] == ["O"]
    assert call["formula"] == "TiO2"
    assert call["band_gap"] == (1.5, 3.0)
    assert call["energy_above_hull"] == (0, 0.05)
    assert call["chunk_size"] == 1 and call["num_chunks"] == 1
    assert result.possibly_truncated
    assert result.materials[0].data_kind == "computed"
    assert result.materials[0].data_version == "test-version"
    assert result.materials[0].calculation_provenance[0]["task_id"] == "mp-999999998"
    assert result.units["energy_above_hull"] == "eV/atom"


def test_empty_query_is_valid(settings, mp_client):
    mp_client.materials.summary.search.return_value = []
    result = MaterialsProjectService(settings).search(MaterialQuery())
    assert result.materials == [] and not result.possibly_truncated
    assert export_csv(result).startswith("material_id,formula,band_gap_eV")


def test_version_failure_preserves_results(settings, mp_client):
    mp_client.db_version = None
    result = MaterialsProjectService(settings).search(MaterialQuery())
    assert result.materials[0].data_version is None


def test_missing_property_is_not_invented(settings, mp_client):
    mp_client.materials.summary.search.return_value[0].pop("band_gap")
    result = MaterialsProjectService(settings).search(MaterialQuery())
    assert result.materials[0].band_gap is None


def test_upstream_failure_does_not_expose_secret(settings, mp_client, caplog):
    mp_client.materials.summary.search.side_effect = RuntimeError("test-only-key")
    with pytest.raises(ServiceError) as caught:
        MaterialsProjectService(settings).search(MaterialQuery())
    assert "test-only-key" not in str(caught.value)
    assert "test-only-key" not in caplog.text


def test_invalid_upstream_value_is_rejected(settings, mp_client):
    mp_client.materials.summary.search.return_value[0]["band_gap"] = float("nan")
    with pytest.raises(ServiceError, match="校验失败"):
        MaterialsProjectService(settings).search(MaterialQuery())


@pytest.mark.api
def test_api_snapshot_survives_store_recreation(settings, mp_client):
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
            response = client.post("/api/v1/materials/search", json={"formula": "TiO2"})
            assert response.status_code == 200
            query_id = response.json()["query_id"]
            from app.core.config import LOCAL_TENANT_ID, tenant_data_dir

            stored = QueryStore(tenant_data_dir(settings, LOCAL_TENANT_ID)).load(query_id)
            assert stored.query.formula == "TiO2"
            assert client.get(f"/api/v1/materials/queries/{query_id}").json() == response.json()
            exported = client.get(f"/api/v1/materials/queries/{query_id}/csv")
            assert exported.status_code == 200
            assert "band_gap_eV" in exported.text
            assert "test-version" in exported.text
            assert "materialsproject.org/materials/mp-999999999" in exported.text
            assert client.get(f"/api/v1/materials/queries/{uuid4()}").status_code == 404
            assert client.get("/api/v1/materials/queries/not-a-uuid").status_code == 422
            assert client.post("/api/v1/materials/search", json={"limit": 0}).status_code == 422
            assert mp_client.materials.summary.search.call_count == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.api
def test_api_missing_key(workspace_dir, monkeypatch):
    monkeypatch.delenv("MP_API_KEY", raising=False)
    settings = Settings(_env_file=None, mp_api_key=None, data_dir=workspace_dir)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/materials/search", json={})
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "mp_not_configured"
        assert not (workspace_dir / "tenants" / "local" / "material_queries").exists()
    finally:
        app.dependency_overrides.clear()


def test_storage_write_failure_returns_explicit_error(settings, mp_client):
    result = MaterialsProjectService(settings).search(MaterialQuery())
    settings.data_dir = settings.data_dir / "blocked"
    settings.data_dir.write_text("file prevents directory creation")
    with pytest.raises(ServiceError, match="保存失败"):
        QueryStore(settings.data_dir).save(result)


def test_secret_configuration_not_displayed(settings):
    assert "test-only-key" not in repr(settings)


def test_sdk_import_and_signature():
    # Validates the installed dependency import, not a remote call.
    import inspect

    from mp_api.client.core.client import BaseRester
    from mp_api.client.routes.materials.summary import SummaryRester

    assert "timeout" in inspect.signature(BaseRester).parameters
    parameters = inspect.signature(SummaryRester.search).parameters
    assert {
        "elements",
        "formula",
        "band_gap",
        "energy_above_hull",
        "num_chunks",
        "chunk_size",
        "fields",
    }.issubset(parameters)


def test_material_details_and_missing_record(settings, mp_client):
    service = MaterialsProjectService(settings)
    assert service.get_details("mp-999999999").formula == "TiO2"
    assert mp_client.materials.summary.search.call_args.kwargs["material_ids"] == ["mp-999999999"]
    mp_client.materials.summary.search.return_value = []
    with pytest.raises(ServiceError) as caught:
        service.get_details("mp-999999999")
    assert caught.value.status_code == 404


def test_crystal_metrics_and_missing_structure(settings, mp_client):
    from pymatgen.core import Lattice, Structure

    # Synthetic unit cell solely tests deterministic geometry serialization.
    structure = Structure(Lattice.cubic(3), ["Zn", "O"], [[0, 0, 0], [0.5, 0.5, 0.5]])
    mp_client.get_structure_by_material_id.return_value = structure
    service = MaterialsProjectService(settings)
    result = service.get_structure("mp-999999999")
    assert result.formula == "ZnO" and result.site_count == 2
    assert result.volume == pytest.approx(27)
    assert result.lattice_angles == (90, 90, 90)
    assert result.units["volume"] == "angstrom^3"
    assert Structure.from_dict(result.structure) == structure
    mp_client.get_structure_by_material_id.return_value = None
    with pytest.raises(ServiceError) as caught:
        service.get_structure("mp-999999999")
    assert caught.value.status_code == 404


def test_invalid_id_does_not_query_provider(settings, mp_client):
    with pytest.raises(ServiceError):
        MaterialsProjectService(settings).get_details("../bad-id")
    mp_client.materials.summary.search.assert_not_called()


def test_alphanumeric_ids_survive_snapshot_and_csv(settings, mp_client):
    mp_client.materials.summary.search.return_value[0]["material_id"] = "mp-testabc"
    result = MaterialsProjectService(settings).search(MaterialQuery())
    store = QueryStore(settings.data_dir)
    store.save(result)
    restored = QueryStore(settings.data_dir).load(result.query_id)
    assert restored == result
    assert "mp-testabc" in export_csv(restored)
    assert restored.materials[0].source_url.endswith("/mp-testabc")


def test_sdk_factory_does_not_write_lazy_proxy_attributes(settings, monkeypatch):
    from types import SimpleNamespace

    from app.science.materials_project import create_mp_client

    client = SimpleNamespace(materials=SimpleNamespace(summary=object()))
    factory = MagicMock(return_value=client)
    monkeypatch.setattr("mp_api.client.MPRester", factory)
    assert create_mp_client(settings) is client
    assert factory.call_args.kwargs["timeout"] == settings.mp_timeout_seconds
    assert "monty_decode" not in factory.call_args.kwargs
