"""Exercise the real LangGraph loop with explicit non-scientific test tools."""

import json

import pytest
from fastapi.testclient import TestClient

from app.agents.research import ResearchAgent, validate_agent_claims
from app.core.config import Settings, get_settings
from app.core.errors import ServiceError
from app.main import app
from app.schemas.agent import AgentDraft, AgentRequest, ToolRecord


def call(name="search_papers", arguments=None):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "fixture-call",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(arguments or {"question": "test"}),
                },
            }
        ],
    }


def test_langgraph_loop_tools_evidence_and_persisted_http(workspace_dir, monkeypatch):
    settings = Settings(_env_file=None, data_dir=workspace_dir)
    responses = iter(
        [
            call(),
            {"role": "assistant", "content": "ready"},
            {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "claims": [
                            {
                                "text": "Fixture answer",
                                "citations": [{"source_id": 1, "start_line": 5, "end_line": 5}],
                            }
                        ]
                    }
                ),
            },
        ]
    )
    monkeypatch.setattr(
        "app.services.chat_service.ChatService.complete", lambda *args, **kwargs: next(responses)
    )
    monkeypatch.setattr(
        ResearchAgent, "execute", lambda *args: {"evidence": "explicit test fixture"}
    )
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post("/api/agent/run", json={"question": "fixture question"})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "answered" and data["model_steps"] == 2
            assert data["answer"] == "Fixture answer [T1]"
            assert data["tools"][0]["name"] == "search_papers"
            assert data["claims"][0]["citations"][0]["quote"] == "explicit test fixture"
            assert client.get(f"/api/agent/runs/{data['run_id']}").json() == data
    finally:
        app.dependency_overrides.clear()


def test_tool_steps_are_bounded(workspace_dir, monkeypatch):
    agent = ResearchAgent(Settings(_env_file=None, data_dir=workspace_dir))
    counts = {"plan": 0, "tool": 0}

    def complete(messages, **kwargs):
        if kwargs.get("json_output"):
            return {"content": '{"claims":[]}'}
        counts["plan"] += 1
        return call()

    def execute(*args):
        counts["tool"] += 1
        return {"fixture": True}

    monkeypatch.setattr(agent.chat, "complete", complete)
    monkeypatch.setattr(agent, "execute", execute)
    result = agent.run(AgentRequest(question="test", max_steps=2))
    assert result.status == "limit_reached"
    assert counts == {"plan": 2, "tool": 2}


def test_unknown_tool_and_bad_arguments_rejected(workspace_dir):
    agent = ResearchAgent(Settings(_env_file=None, data_dir=workspace_dir))
    request = AgentRequest(question="fixture")
    with pytest.raises(ServiceError) as caught:
        agent.execute("run_shell", {"command": "test"}, request)
    assert caught.value.code == "unknown_tool"
    with pytest.raises(ValueError):
        agent.execute("get_structure", {"material_id": "invalid"}, request)


@pytest.mark.parametrize("status,quote", [("error", "test"), ("ok", "invented")])
def test_agent_rejects_failed_source_and_fabricated_quote(status, quote):
    draft = AgentDraft.model_validate(
        {"claims": [{"text": "fixture", "citations": [{"source_id": 1, "quote": quote}]}]}
    )
    with pytest.raises(ValueError):
        validate_agent_claims(
            draft,
            [ToolRecord(source_id=1, name="test", arguments={}, status=status, content="test")],
        )


def test_nested_original_text_is_decoded_before_quote_matching():
    draft = AgentDraft.model_validate(
        {
            "claims": [
                {
                    "text": "fixture",
                    "citations": [{"source_id": 1, "quote": "first line\nsecond line"}],
                }
            ]
        }
    )
    record = ToolRecord(
        source_id=1,
        name="test",
        arguments={},
        status="ok",
        content=json.dumps({"text": "first line\nsecond line"}),
    )
    validate_agent_claims(draft, [record])


def test_material_tool_requires_explicit_formula_or_null():
    from app.agents.research import AgentMaterialQuery

    with pytest.raises(ValueError):
        AgentMaterialQuery(elements=["Ti", "O"])
    assert AgentMaterialQuery(formula="TiO2").formula == "TiO2"
    assert AgentMaterialQuery(formula=None, elements=["O"]).formula is None


def test_unavailable_dependency_stops_model_retries_and_keeps_failure_trace(
    workspace_dir, monkeypatch
):
    agent = ResearchAgent(Settings(_env_file=None, data_dir=workspace_dir))
    model_calls = []

    def complete(*args, **kwargs):
        model_calls.append(kwargs)
        return call()

    def execute(*args):
        raise ServiceError("database_unavailable", "Database test fixture is unavailable", 503)

    monkeypatch.setattr(agent.chat, "complete", complete)
    monkeypatch.setattr(agent, "execute", execute)
    with pytest.raises(ServiceError, match="Database test fixture"):
        agent.run(AgentRequest(question="fixture", max_steps=6))
    assert len(model_calls) == 1
    trace_path = next((workspace_dir / "agent_runs").glob("*.failure.json"))
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["error"] == "database_unavailable"
    assert trace["tools"][0]["status"] == "error"


def test_citation_repair_is_bounded_and_does_not_repeat_tools(workspace_dir, monkeypatch):
    agent = ResearchAgent(Settings(_env_file=None, data_dir=workspace_dir))

    def answer(line):
        return {
            "content": json.dumps(
                {
                    "claims": [
                        {
                            "text": "Fixture answer",
                            "citations": [{"source_id": 1, "start_line": line, "end_line": line}],
                        }
                    ]
                }
            )
        }

    responses = iter([call(), {"content": "ready"}, answer(999), answer(5)])
    monkeypatch.setattr(agent.chat, "complete", lambda *a, **k: next(responses))
    tool_calls = []

    def execute(*args):
        tool_calls.append(args)
        return {"evidence": "explicit test fixture"}

    monkeypatch.setattr(agent, "execute", execute)
    result = agent.run(AgentRequest(question="fixture"))
    assert result.claims[0].citations[0].quote == "explicit test fixture"
    assert len(tool_calls) == 1
    attempts = list((workspace_dir / "agent_runs").glob("*.candidate-*.json"))
    assert len(attempts) == 2


def test_missing_from_excerpts_does_not_imply_absent_from_entire_paper():
    record = ToolRecord(
        source_id=1, name="fixture", arguments={}, status="ok", content="Evidence test fixture"
    )
    draft = AgentDraft.model_validate(
        {
            "claims": [
                {
                    "text": "该论文未提供制备条件。",
                    "citations": [{"source_id": 1, "quote": "Evidence test fixture"}],
                }
            ]
        }
    )
    with pytest.raises(ValueError, match="论文全文"):
        validate_agent_claims(draft, [record])
    draft.claims[0].text = "当前检索片段未提供制备条件。"
    validate_agent_claims(draft, [record])


def test_source_context_never_advertises_an_oversized_quote():
    from app.agents.research import source_context
    from app.schemas.selection import LineRange
    from app.services.evidence_service import copy_range

    text = "short\n" + "x" * 4000 + "\nsmall\nlast"
    context = source_context(text)
    for interval in context["allowed_ranges"]:
        assert len(copy_range(text, LineRange(**interval))) <= 3000
    assert context["allowed_ranges"] == [
        {"start_line": 1, "end_line": 1},
        {"start_line": 3, "end_line": 4},
    ]


def test_citation_cannot_join_two_unrelated_excerpts():
    from app.agents.research import resolve_answer
    from app.schemas.selection import SelectedAnswer

    record = ToolRecord(
        source_id=1,
        name="fixture",
        arguments={},
        status="ok",
        content='{"first": "alpha", "second": "beta"}',
    )
    selected = SelectedAnswer.model_validate(
        {
            "claims": [
                {"text": "fixture", "citations": [{"source_id": 1, "start_line": 3, "end_line": 5}]}
            ]
        }
    )
    with pytest.raises(ValueError, match="证据区间"):
        resolve_answer(selected, [record])


@pytest.mark.parametrize(
    "claim", ["该材料使用 GGA/PBE 计算。", "该值来自第一性原理计算。", "Method was DFT."]
)
def test_computed_kind_does_not_prove_a_calculation_method(claim):
    record = ToolRecord(
        source_id=1,
        name="search_materials",
        arguments={},
        status="ok",
        content='{"data_kind":"computed","band_gap":2.8}',
    )
    draft = AgentDraft.model_validate(
        {"claims": [{"text": claim, "citations": [{"source_id": 1, "quote": record.content}]}]}
    )
    with pytest.raises(ValueError):
        validate_agent_claims(draft, [record])
    draft.claims[0].text = "该记录属于计算数据。"
    validate_agent_claims(draft, [record])


def test_explicit_functional_provenance_can_be_cited():
    record = ToolRecord(
        source_id=1,
        name="fixture",
        arguments={},
        status="ok",
        content="Synthetic calculation_method: GGA/PBE",
    )
    draft = AgentDraft.model_validate(
        {
            "claims": [
                {
                    "text": "Synthetic method is GGA/PBE.",
                    "citations": [{"source_id": 1, "quote": record.content}],
                }
            ]
        }
    )
    validate_agent_claims(draft, [record])


def test_not_declared_in_paper_is_also_an_unsupported_full_paper_absence_claim():
    record = ToolRecord(
        source_id=1, name="fixture", arguments={}, status="ok", content="Synthetic excerpt"
    )
    draft = AgentDraft.model_validate(
        {
            "claims": [
                {
                    "text": "原文未声明可以直接比较。",
                    "citations": [{"source_id": 1, "quote": "Synthetic excerpt"}],
                }
            ]
        }
    )
    with pytest.raises(ValueError, match="论文全文"):
        validate_agent_claims(draft, [record])


def test_reported_negative_observation_is_not_a_full_paper_omission_claim():
    record = ToolRecord(
        source_id=1,
        name="fixture",
        arguments={},
        status="ok",
        content="Synthetic observation: no transition was observed.",
    )
    draft = AgentDraft.model_validate(
        {
            "claims": [
                {
                    "text": "该研究未观察到相变。",
                    "citations": [{"source_id": 1, "quote": record.content}],
                }
            ]
        }
    )
    validate_agent_claims(draft, [record])
