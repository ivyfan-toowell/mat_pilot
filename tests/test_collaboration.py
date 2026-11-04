"""Real workflow graph with synthetic expert evidence and deterministic model doubles."""

import json
import threading

import pytest
from fastapi.testclient import TestClient

from app.agents.collaboration import (
    Budget,
    CollaborativeAgent,
    route_workflow,
    validate_quantities,
    validate_review,
)
from app.core.config import Settings, get_settings
from app.core.errors import ServiceError
from app.main import app
from app.schemas.agent import AgentDraft, AgentRequest, ReviewReport, WorkPlan


def plan(dependent=False):
    return {
        "steps": [
            {
                "role": "materials",
                "goal": "Collect synthetic materials fixture",
                "required_tools": ["search_materials"],
                "depends_on": ["literature"] if dependent else [],
            },
            {
                "role": "literature",
                "goal": "Collect synthetic paper fixture",
                "required_tools": ["search_papers"],
                "depends_on": [],
            },
        ]
    }


def draft():
    return {
        "claims": [
            {
                "text": "Material fixture conclusion",
                "citations": [{"source_id": 1, "start_line": 5, "end_line": 5}],
            },
            {
                "text": "Paper fixture conclusion",
                "citations": [{"source_id": 2, "start_line": 5, "end_line": 5}],
            },
        ]
    }


def review(supported=True):
    return {
        "checks": [
            {
                "claim_index": i,
                "supported": supported,
                "reason": "Synthetic supporting evidence"
                if supported
                else "Unsupported synthetic interpretation",
            }
            for i in (1, 2)
        ]
    }


def configure(agent, monkeypatch, *, dependent=False, reject_times=0, barrier=None):
    counts = {"review": 0, "analysis": 0, "tools": 0}
    order = []

    def complete(messages, **kwargs):
        prompt = messages[0]["content"]
        if "规划智能体" in prompt:
            return {"content": json.dumps(plan(dependent))}
        if "分析智能体" in prompt:
            counts["analysis"] += 1
            return {"content": json.dumps(draft())}
        if "独立复核智能体" in prompt:
            counts["review"] += 1
            return {"content": json.dumps(review(counts["review"] > reject_times))}
        name = kwargs["forced_tool"]
        if name == "search_materials" and dependent:
            data = json.loads(messages[1]["content"])
            assert data["prior_tools"][0]["name"] == "search_papers"
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "fixture-call",
                    "type": "function",
                    "function": {"name": name, "arguments": "{}"},
                }
            ],
        }

    def execute(name, args, request):
        if barrier:
            barrier.wait(timeout=5)
        counts["tools"] += 1
        order.append(name)
        return {
            "evidence": "Synthetic material evidence"
            if name == "search_materials"
            else "Synthetic paper evidence"
        }

    monkeypatch.setattr(agent.chat, "complete", complete)
    monkeypatch.setattr(agent.executor, "execute", execute)
    return counts, order


def request(**updates):
    return AgentRequest(
        question="Synthetic comparison task",
        workflow_mode="collaborative",
        required_tools=["search_materials", "search_papers"],
        **updates,
    )


def test_supervisor_keeps_simple_tasks_single_and_routes_cross_domain_tasks():
    assert route_workflow(AgentRequest(question="查找论文", workflow_mode="auto"))[0] == "single"
    assert (
        route_workflow(
            AgentRequest(question="比较 Materials Project 计算带隙与论文实验", workflow_mode="auto")
        )[0]
        == "collaborative"
    )
    assert (
        route_workflow(AgentRequest(question="Materials Project 与论文", workflow_mode="single"))[0]
        == "single"
    )


def test_plan_rejects_cycles_wrong_roles_and_tools():
    value = plan(True)
    value["steps"][1]["depends_on"] = ["materials"]
    with pytest.raises(ValueError):
        WorkPlan.model_validate(value)
    value = plan()
    value["steps"][0]["required_tools"] = ["search_papers"]
    with pytest.raises(ValueError):
        WorkPlan.model_validate(value)


def test_parallel_experts_review_and_durable_http_readback(workspace_dir, monkeypatch):
    settings = Settings(_env_file=None, data_dir=workspace_dir)
    agent = CollaborativeAgent(settings)
    counts, _ = configure(agent, monkeypatch, barrier=threading.Barrier(2))
    result = agent.run(request(), "fixture routing")
    assert result.status == "answered" and result.workflow_mode == "collaborative"
    assert counts == {"review": 1, "analysis": 1, "tools": 2}
    assert result.collaboration.execution_mode == "parallel"
    assert result.collaboration.model_calls == 5 and result.collaboration.tool_calls == 2
    assert {metric.role for metric in result.collaboration.roles} == {
        "planner",
        "materials",
        "literature",
        "analysis",
        "reviewer",
    }
    assert sum(metric.model_calls for metric in result.collaboration.roles) == 5
    assert [tool.source_id for tool in result.tools] == [1, 2]
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            assert client.get(f"/api/agent/runs/{result.run_id}").json() == result.model_dump(
                mode="json"
            )
            checkpoint = client.get(f"/api/agent/runs/{result.run_id}/checkpoint").json()
            assert checkpoint["phase"] == "completed" and len(checkpoint["tools"]) == 2
    finally:
        app.dependency_overrides.clear()


def test_dependent_experts_run_in_order_with_prior_results(workspace_dir, monkeypatch):
    agent = CollaborativeAgent(Settings(_env_file=None, data_dir=workspace_dir))
    _, order = configure(agent, monkeypatch, dependent=True)
    result = agent.run(request(), "fixture")
    assert order == ["search_papers", "search_materials"]
    assert result.collaboration.execution_mode == "sequential"


def test_reviewer_can_reject_then_repair_without_repeating_tools(workspace_dir, monkeypatch):
    agent = CollaborativeAgent(Settings(_env_file=None, data_dir=workspace_dir))
    counts, _ = configure(agent, monkeypatch, reject_times=1)
    result = agent.run(request(), "fixture")
    assert counts == {"review": 2, "analysis": 2, "tools": 2}
    assert len(result.collaboration.reviews) == 2 and result.collaboration.model_calls == 7
    assert result.collaboration.reviews[0].checks[0].supported is False


def test_repeated_review_rejection_never_publishes_an_answer(workspace_dir, monkeypatch):
    agent = CollaborativeAgent(Settings(_env_file=None, data_dir=workspace_dir))
    counts, _ = configure(agent, monkeypatch, reject_times=99)
    with pytest.raises(ServiceError) as error:
        agent.run(request(), "fixture")
    assert error.value.code == "agent_review_failed" and counts["review"] == 2
    checkpoint_path = next((workspace_dir / "agent_runs").glob("*.checkpoint.json"))
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["phase"] == "failed" and checkpoint["error"] == "agent_review_failed"
    assert not checkpoint_path.with_name(checkpoint_path.name.replace(".checkpoint", "")).exists()


def test_shared_model_budget_stops_repair_and_preserves_state(workspace_dir, monkeypatch):
    agent = CollaborativeAgent(Settings(_env_file=None, data_dir=workspace_dir))
    counts, _ = configure(agent, monkeypatch, reject_times=1)
    with pytest.raises(ServiceError) as error:
        agent.run(request(max_model_calls=5), "fixture")
    assert error.value.code == "agent_budget_exhausted" and counts["analysis"] == 1
    saved = json.loads(
        next((workspace_dir / "agent_runs").glob("*.checkpoint.json")).read_text(encoding="utf-8")
    )
    assert saved["model_calls"] == 5 and saved["phase"] == "failed"


def test_budget_has_tool_limit_and_cooperative_deadline():
    budget = Budget(AgentRequest(question="fixture"))
    for _ in range(8):
        budget.charge("tool")
    with pytest.raises(ServiceError, match="8"):
        budget.charge("tool")
    budget.deadline = 0
    with pytest.raises(ServiceError) as error:
        budget.check()
    assert error.value.code == "agent_timeout"


def test_reviewer_must_check_every_claim_once():
    evidence = AgentDraft.model_validate(
        {"claims": [{"text": "fixture", "citations": [{"source_id": 1, "quote": "fixture"}]}]}
    )
    assert validate_review(
        ReviewReport.model_validate(
            {"checks": [{"claim_index": 1, "supported": True, "reason": "fixture"}]}
        ),
        evidence,
    )
    with pytest.raises(ValueError):
        validate_review(ReviewReport.model_validate(review()), evidence)


def test_scientific_numbers_must_exist_in_citations_with_rounding_allowed():
    evidence = AgentDraft.model_validate(
        {
            "claims": [
                {
                    "text": "Synthetic 2.89 eV",
                    "citations": [{"source_id": 1, "quote": 'Synthetic {"gap":2.8899}'}],
                }
            ]
        }
    )
    validate_quantities(evidence)
    evidence.claims[0].text = "Synthetic 7.88 eV"
    with pytest.raises(ValueError):
        validate_quantities(evidence)


def test_filter_bound_requires_its_own_quoted_literal():
    evidence = AgentDraft.model_validate(
        {
            "claims": [
                {
                    "text": "Synthetic hull <= 0.05 eV/atom",
                    "citations": [
                        {"source_id": 1, "quote": 'Synthetic {"energy_above_hull":0.01649}'}
                    ],
                }
            ]
        }
    )
    with pytest.raises(ValueError):
        validate_quantities(evidence)
    evidence.claims[0].citations[0].quote = 'Synthetic {"energy_above_hull_max":0.05}'
    validate_quantities(evidence)


def test_role_cannot_execute_other_domain_tool(workspace_dir, monkeypatch):
    agent = CollaborativeAgent(Settings(_env_file=None, data_dir=workspace_dir))
    configure(agent, monkeypatch)

    # Domain validation is enforced even if a model ignores forced_tool.
    def invalid(*args, **kwargs):
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "bad", "function": {"name": "search_papers", "arguments": "{}"}}],
        }

    monkeypatch.setattr(agent.chat, "complete", invalid)
    step = WorkPlan.model_validate(plan()).steps[0]
    monkeypatch.setattr(
        agent.executor, "execute", lambda *args: pytest.fail("Cross-domain tool must not run")
    )
    with pytest.raises(ServiceError) as error:
        agent.expert(step, request(max_steps=1), Budget(request()), [], workspace_dir, "fixture")
    assert error.value.code == "required_tool_incomplete"
