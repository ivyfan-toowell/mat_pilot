"""定义科研任务、工具轨迹、引用结论、协作计划与复核结果的数据结构。"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

ToolName = Literal[
    "search_materials",
    "get_material_details",
    "get_structure",
    "compare_materials",
    "search_papers",
    "read_experiments",
    "search_academic_papers",
]
MATERIAL_TOOLS = {"search_materials", "get_material_details", "get_structure", "compare_materials"}
LITERATURE_TOOLS = {"search_papers", "read_experiments", "search_academic_papers"}


class AgentCheckpoint(BaseModel):
    """协作阶段快照；允许扩展字段以兼容历史落盘。"""

    model_config = {"extra": "allow"}

    run_id: str | None = None
    phase: str | None = None
    model_calls: int | None = None
    tool_calls: int | None = None


class AgentRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000, pattern=r"\S")
    document_id: UUID | None = None
    max_steps: int = Field(default=4, ge=1, le=6)
    workflow_mode: Literal["single", "auto", "collaborative"] = "single"
    max_model_calls: int = Field(default=10, ge=5, le=16)
    time_budget_seconds: int = Field(default=240, ge=30, le=600)
    required_tools: list[
        Literal[
            "search_materials",
            "get_material_details",
            "get_structure",
            "compare_materials",
            "search_papers",
            "read_experiments",
            "search_academic_papers",
        ]
    ] = Field(default_factory=list, max_length=7)


class ToolRecord(BaseModel):
    source_id: int
    name: str
    arguments: dict
    status: Literal["ok", "error"]
    content: str


class AgentCitation(BaseModel):
    source_id: int = Field(ge=1, le=8)
    quote: str = Field(min_length=1, max_length=3000, pattern=r"\S")


class AgentClaim(BaseModel):
    text: str = Field(min_length=1, max_length=3000)
    citations: list[AgentCitation] = Field(min_length=1, max_length=8)


class AgentDraft(BaseModel):
    claims: list[AgentClaim] = Field(default_factory=list, max_length=20)


class PlanStep(BaseModel):
    role: Literal["materials", "literature"]
    goal: str = Field(min_length=1, max_length=1500)
    required_tools: list[ToolName] = Field(min_length=1, max_length=4)
    depends_on: list[Literal["materials", "literature"]] = Field(default_factory=list, max_length=1)

    @model_validator(mode="after")
    def validate_role(self):
        allowed = MATERIAL_TOOLS if self.role == "materials" else LITERATURE_TOOLS
        if not set(self.required_tools).issubset(allowed) or self.role in self.depends_on:
            raise ValueError("tool ownership or dependency invalid")
        self.required_tools = list(dict.fromkeys(self.required_tools))
        return self


class WorkPlan(BaseModel):
    steps: list[PlanStep] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_dependencies(self):
        if {step.role for step in self.steps} != {"materials", "literature"}:
            raise ValueError("both expert roles required")
        if all(step.depends_on for step in self.steps):
            raise ValueError("cyclic expert dependencies")
        return self


class ClaimReview(BaseModel):
    claim_index: int = Field(ge=1, le=20)
    supported: bool
    reason: str = Field(min_length=1, max_length=1000)


class ReviewReport(BaseModel):
    checks: list[ClaimReview] = Field(min_length=1, max_length=20)


class RoleMetric(BaseModel):
    role: str
    model_calls: int = Field(ge=0)
    elapsed_ms: float = Field(ge=0)


class CollaborationTrace(BaseModel):
    plan: WorkPlan
    execution_mode: Literal["parallel", "sequential"]
    model_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0, le=8)
    reviews: list[ReviewReport] = Field(default_factory=list, max_length=2)
    roles: list[RoleMetric] = Field(default_factory=list)


class AgentResult(BaseModel):
    run_id: UUID
    created_at: datetime
    question: str
    status: Literal["answered", "insufficient_evidence", "limit_reached"]
    answer: str
    claims: list[AgentClaim] = Field(default_factory=list)
    tools: list[ToolRecord]
    model_steps: int
    workflow_mode: Literal["single", "collaborative"] = "single"
    routing_reason: str | None = None
    collaboration: CollaborationTrace | None = None
    warnings: list[str] = Field(
        default_factory=lambda: [
            "计算属性与论文实验估计值不能直接等同；工具来源和引文校验不能替代科研审核。"
        ]
    )


class AgentRunSummary(BaseModel):
    run_id: UUID
    created_at: datetime
    question: str
    status: Literal["answered", "insufficient_evidence", "limit_reached"]
    workflow_mode: Literal["single", "collaborative"]
