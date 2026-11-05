"""Synthetic metadata/API contracts, separate from live scientific acceptance."""

import json
import logging
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents.claims import validate_agent_claims
from app.agents.research import ResearchAgent
from app.core.config import Settings, get_settings
from app.core.errors import ServiceError
from app.main import app
from app.schemas.agent import AgentDraft, AgentRequest, ToolRecord
from app.schemas.literature import LiteratureQuery
from app.services.literature_service import LiteratureService, LiteratureStore, paper_from_work

KEY = "synthetic-private-openalex-key"


def work(**updates):
    return {
        "id": "https://openalex.org/W12345",
        "title": "Synthetic metadata fixture",
        "doi": "https://doi.org/10.9999/FIXTURE",
        "publication_year": 2024,
        "publication_date": "2024-03-01",
        "cited_by_count": 2,
        "authorships": [{"author": {"display_name": "Test Author"}}],
        "open_access": {"is_oa": True, "oa_status": "green"},
        "primary_location": {
            "source": {"display_name": "Synthetic Journal"},
            "license": "publisher-license",
            "is_oa": False,
            "landing_page_url": "https://example.invalid/publisher",
        },
        "best_oa_location": {
            "is_oa": True,
            "license": "cc-by",
            "version": "acceptedVersion",
            "landing_page_url": "https://example.invalid/repository",
            "pdf_url": "https://example.invalid/paper.pdf",
        },
        **updates,
    }


def settings(folder, **updates):
    return Settings(_env_file=None, data_dir=folder, openalex_api_key=KEY, **updates)


def mock_http(monkeypatch, handler):
    original = httpx.Client
    calls = []

    def handle(request):
        calls.append(request)
        return handler(request, len(calls))

    monkeypatch.setattr(
        "app.services.literature_service.httpx.Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    return calls


def envelope(*works, count=None):
    return {
        "meta": {"count": count if count is not None else len(works), "cost_usd": 0.001},
        "results": list(works),
    }


@pytest.mark.parametrize(
    "data",
    [
        {"query": " "},
        {"query": "a" * 301},
        {"query": "test", "limit": 21},
        {"query": "test", "year_from": 2025, "year_to": 2024},
        {"query": "test", "api_key": "should-not-be-in-user-arguments"},
    ],
)
def test_query_rejects_invalid_filters_and_credential_arguments(data):
    with pytest.raises(ValueError):
        LiteratureQuery.model_validate(data)


def test_missing_key_fails_before_network(workspace_dir, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Missing key must fail before creating an HTTP client")

    monkeypatch.setattr("app.services.literature_service.httpx.Client", forbidden)
    with pytest.raises(ServiceError) as error:
        LiteratureService(Settings(_env_file=None, data_dir=workspace_dir)).search(
            LiteratureQuery(query="test")
        )
    assert error.value.code == "openalex_not_configured"


def test_search_preserves_filters_deduplicates_and_never_persists_key(
    workspace_dir, monkeypatch, caplog
):
    def handler(request, attempt):
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        assert KEY not in str(request.url) and "api_key" not in request.url.params
        assert (
            request.url.params["filter"]
            == "is_oa:true,from_publication_date:2020-01-01,to_publication_date:2026-12-31"
        )
        assert request.url.params["sort"] == "publication_date:desc"
        assert request.url.params["search"] == "TiO2 optical"
        return httpx.Response(
            200, json=envelope(work(), work(id="https://openalex.org/W98765"), count=8)
        )

    calls = mock_http(monkeypatch, handler)
    with caplog.at_level(logging.INFO):
        result = LiteratureService(settings(workspace_dir)).search(
            LiteratureQuery(
                query=" TiO2 optical ",
                year_from=2020,
                year_to=2026,
                open_access_only=True,
                sort="newest",
                limit=2,
            )
        )
    assert len(calls) == 1 and len(result.papers) == 1
    assert result.possibly_truncated and result.papers[0].doi == "10.9999/fixture"
    assert result.metadata_only and result.papers[0].data_kind == "bibliographic_metadata"
    from app.core.config import LOCAL_TENANT_ID, tenant_data_dir

    root = tenant_data_dir(settings(workspace_dir), LOCAL_TENANT_ID)
    assert LiteratureStore(root).load(result.query_id) == result
    assert KEY not in result.model_dump_json() and KEY not in caplog.text
    assert not list((root / "literature_queries").glob("*.tmp"))


def test_doi_lookup_uses_exact_filter_instead_of_keyword_search(workspace_dir, monkeypatch):
    def handler(request, attempt):
        assert "search" not in request.url.params
        assert request.url.params["filter"] == "doi:10.9999/fixture"
        return httpx.Response(200, json=envelope(work()))

    mock_http(monkeypatch, handler)
    result = LiteratureService(settings(workspace_dir)).search(
        LiteratureQuery(query="https://doi.org/10.9999/FIXTURE")
    )
    assert result.papers[0].doi_url == "https://doi.org/10.9999/fixture"


def test_pdf_and_license_belong_to_same_copy_and_missing_values_stay_empty():
    paper = paper_from_work(work())
    assert paper.license == "cc-by" and paper.version == "acceptedVersion"
    assert paper.pdf_url == "https://example.invalid/paper.pdf"
    missing = paper_from_work({"id": "https://openalex.org/W12345"})
    assert missing.title is None and missing.doi is None and missing.authors == []
    assert missing.is_oa is None and missing.cited_by_count is None
    closed = paper_from_work(
        work(
            best_oa_location=None,
            primary_location={"is_oa": False, "pdf_url": "https://example.invalid/paywalled.pdf"},
        )
    )
    assert closed.pdf_url is None
    unsafe = paper_from_work(
        work(
            best_oa_location={
                "is_oa": True,
                "pdf_url": "javascript:alert(1)",
                "landing_page_url": "file:///C:/private",
            }
        )
    )
    assert unsafe.pdf_url is None and unsafe.landing_page_url is None


@pytest.mark.parametrize("status", [401, 403])
def test_auth_error_is_not_retried_or_disclosed(workspace_dir, monkeypatch, status):
    calls = mock_http(
        monkeypatch, lambda *args: httpx.Response(status, text=f"provider body {KEY}")
    )
    with pytest.raises(ServiceError) as error:
        LiteratureService(settings(workspace_dir)).search(LiteratureQuery(query="fixture"))
    assert len(calls) == 1 and error.value.code == "openalex_auth_failed"
    assert KEY not in str(error.value)


def test_transient_failure_retries_once_then_saves_success(workspace_dir, monkeypatch):
    delays = []
    monkeypatch.setattr("app.services.literature_service.time.sleep", delays.append)
    calls = mock_http(
        monkeypatch,
        lambda request, n: (
            httpx.Response(503) if n == 1 else httpx.Response(200, json=envelope(work()))
        ),
    )
    result = LiteratureService(settings(workspace_dir)).search(LiteratureQuery(query="fixture"))
    assert len(calls) == 2 and result.attempts == 2 and delays == [0.5]


@pytest.mark.parametrize("retry_after,expected_calls", [("0", 3), ("3600", 1)])
def test_rate_limit_retries_are_bounded_without_long_wait(
    workspace_dir, monkeypatch, retry_after, expected_calls
):
    delays = []
    monkeypatch.setattr("app.services.literature_service.time.sleep", delays.append)
    calls = mock_http(
        monkeypatch, lambda *args: httpx.Response(429, headers={"Retry-After": retry_after})
    )
    with pytest.raises(ServiceError) as error:
        LiteratureService(settings(workspace_dir)).search(LiteratureQuery(query="fixture"))
    assert len(calls) == expected_calls and len(delays) == expected_calls - 1
    assert error.value.code == "openalex_rate_limited"
    assert not (workspace_dir / "tenants" / "local" / "literature_queries").exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"results": "bad", "meta": {"count": 1}},
        envelope({"id": "not-an-openalex-id"}),
        {"results": [work()], "meta": {"count": False}},
    ],
)
def test_invalid_provider_data_is_rejected_not_saved(workspace_dir, monkeypatch, payload):
    mock_http(monkeypatch, lambda *args: httpx.Response(200, json=payload))
    with pytest.raises(ServiceError) as error:
        LiteratureService(settings(workspace_dir)).search(LiteratureQuery(query="fixture"))
    assert error.value.code == "openalex_invalid_response"
    assert not (workspace_dir / "tenants" / "local" / "literature_queries").exists()


def test_provider_cannot_silently_widen_requested_filters(workspace_dir, monkeypatch):
    mock_http(
        monkeypatch, lambda *args: httpx.Response(200, json=envelope(work(publication_year=2010)))
    )
    with pytest.raises(ServiceError) as error:
        LiteratureService(settings(workspace_dir)).search(
            LiteratureQuery(query="fixture", year_from=2020)
        )
    assert error.value.code == "openalex_invalid_response"


@pytest.mark.api
def test_http_search_readback_validation_and_not_found(workspace_dir, monkeypatch):
    mock_http(monkeypatch, lambda *args: httpx.Response(200, json=envelope(work())))
    app.dependency_overrides[get_settings] = lambda: settings(workspace_dir)
    try:
        with TestClient(app) as client:
            assert client.post("/api/v1/literature/search", json={"query": " "}).status_code == 422
            result = client.post("/api/v1/literature/search", json={"query": "fixture"}).json()
            response = client.get(f"/api/v1/literature/queries/{result['query_id']}")
            assert response.status_code == 200 and response.json() == result
            assert KEY not in response.text
            assert client.get(f"/api/v1/literature/queries/{uuid4()}").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_agent_hides_unconfigured_optional_tool_and_fails_before_model(workspace_dir, monkeypatch):
    agent = ResearchAgent(Settings(_env_file=None, data_dir=workspace_dir))
    names = {tool["function"]["name"] for tool in agent.available_tools}
    assert "search_academic_papers" not in names and "search_papers" in names
    monkeypatch.setattr(
        agent.chat, "complete", lambda *args, **kwargs: pytest.fail("No paid call for missing key")
    )
    with pytest.raises(ServiceError) as error:
        agent.run(AgentRequest(question="fixture", required_tools=["search_academic_papers"]))
    assert error.value.code == "openalex_not_configured"


def test_metadata_cannot_be_cited_as_a_measured_band_gap():
    record = ToolRecord(
        source_id=1,
        name="search_academic_papers",
        arguments={},
        status="ok",
        content=json.dumps({"title": "Synthetic 3.42 eV example"}),
    )
    draft = AgentDraft.model_validate(
        {
            "claims": [
                {
                    "text": "Measured gap is 3.42 eV",
                    "citations": [{"source_id": 1, "quote": "Synthetic 3.42 eV example"}],
                }
            ]
        }
    )
    with pytest.raises(ValueError, match="仅有元数据引用"):
        validate_agent_claims(draft, [record])
    draft.claims[0].text = "The indexed title is a synthetic example."
    validate_agent_claims(draft, [record])
