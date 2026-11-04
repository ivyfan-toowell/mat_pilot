"""定义模型选择的来源行号范围、答案和实验记录，由服务端复制原文。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LineRange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class ToolSelection(LineRange):
    source_id: int = Field(ge=1, le=8)


class SelectedClaim(BaseModel):
    text: str = Field(min_length=1, max_length=3000)
    citations: list[ToolSelection] = Field(min_length=1, max_length=8)


class SelectedAnswer(BaseModel):
    claims: list[SelectedClaim] = Field(default_factory=list, max_length=20)


class BlockSelection(LineRange):
    block_id: str


class SelectedExperiment(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    material_formula: str
    sample_label: str
    property_name: Literal["band_gap"]
    property_value: float = Field(ge=0)
    property_unit: Literal["eV"]
    evidence: list[BlockSelection] = Field(min_length=1, max_length=4)
    method_evidence: BlockSelection | None = None
    conditions_evidence: BlockSelection | None = None


class SelectedExperiments(BaseModel):
    experiments: list[SelectedExperiment] = Field(max_length=50)
