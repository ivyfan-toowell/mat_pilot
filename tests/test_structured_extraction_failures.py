"""Regression tests for structured extraction model failure handling."""
from types import SimpleNamespace

import pytest

from app.core.errors import ServiceError
from app.ingestion.structured_extractor import StructuredExperimentExtractor
from test_structured_extractor import paper


@pytest.mark.parametrize(
    ("response", "expected_code"),
    [
        ({"content": ""}, "structured_extraction_empty_response"),
        ({"content": '{"observations": []'}, "structured_extraction_invalid_schema"),
        ({"content": '{"observations": [{"property_value": "invalid"}]}'},
         "structured_extraction_invalid_schema"),
    ],
)
def test_model_failures_do_not_write(monkeypatch, response, expected_code):
    from app.services.chat_service import ChatService

    monkeypatch.setattr(ChatService, "complete", lambda self, *a, **kw: response)
    settings = SimpleNamespace(dashscope_api_key="fake")
    with pytest.raises(ServiceError) as error:
        StructuredExperimentExtractor(settings, "local").extract(paper())
    assert error.value.code == expected_code


def test_model_can_return_no_observations_without_crash(monkeypatch):
    from app.services.chat_service import ChatService

    monkeypatch.setattr(
        ChatService, "complete",
        lambda self, *a, **kw: {"content": '{"observations": []}'},
    )
    rows, warnings = StructuredExperimentExtractor(
        SimpleNamespace(dashscope_api_key="fake"), "local"
    ).extract(paper())
    assert rows == []
    assert warnings == []
