"""科研助手允许调用的工具模式、描述与执行入口。"""

from pathlib import Path

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.core.errors import ServiceError
from app.schemas.agent import AgentRequest
from app.schemas.literature import LiteratureQuery
from app.schemas.material import MATERIAL_ID_PATTERN, ComparisonRequest, MaterialQuery
from app.schemas.retrieval import SearchRequest
from app.science.materials_project import MaterialsProjectService
from app.services.comparison_service import compare_materials
from app.services.document_service import DocumentService
from app.services.literature_service import LiteratureService
from app.services.material_service import QueryStore
from app.services.rag_service import RagService


class PaperSearch(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=6)


class MaterialLookup(BaseModel):
    material_id: str = Field(pattern=MATERIAL_ID_PATTERN)


class NoArguments(BaseModel):
    model_config = {"extra": "forbid"}


class AgentMaterialQuery(MaterialQuery):
    formula: str | None = Field(
        ...,
        description="用户指定确切化学式时必须填写，例如 TiO2。"
        "仅按元素检索时才设为 null；元素条件不能限定化学计量比。",
    )


TOOL_MODELS = {
    "get_material_details": MaterialLookup,
    "compare_materials": ComparisonRequest,
    "search_materials": AgentMaterialQuery,
    "get_structure": MaterialLookup,
    "search_papers": PaperSearch,
    "read_experiments": NoArguments,
    "search_academic_papers": LiteratureQuery,
}
DESCRIPTIONS = {
    "get_material_details": "按单个 MP-ID 实时获取材料的计算属性及其来源。",
    "compare_materials": "比较已保存 query_id 中的候选材料，保留单位和来源。",
    "search_materials": "实时查询 Materials Project 的计算属性，最多返回 10 个候选材料。",
    "get_structure": "按候选材料的 MP-ID 获取晶体结构和晶格参数。",
    "search_papers": "检索带页码的论文原文证据；已选择文献时仅检索该文献。",
    "read_experiments": "读取所选论文中已提取的实验估计值；缺失的方法或条件保持为 null，"
    "结果仍可能需要科研审核。",
    "search_academic_papers": "在线检索 OpenAlex 论文元数据，包括标题、DOI、作者、年份和访问链接。"
    "该工具不读取全文，不能据此确认实验测量值。"
    "请使用简短的英文科研关键词或 DOI 检索，不得编造作者或标识符。",
}
DEPENDENCY_FAILURES = {
    "database_unavailable",
    "database_not_configured",
    "database_driver_missing",
    "schema_not_ready",
    "embedding_config_mismatch",
    "embedding_not_configured",
    "mp_not_configured",
    "openalex_not_configured",
    "openalex_auth_failed",
    "openalex_rate_limited",
    "openalex_unavailable",
}
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": DESCRIPTIONS[name],
            "parameters": model.model_json_schema(),
        },
    }
    for name, model in TOOL_MODELS.items()
]


def execute_tool(
    settings: Settings,
    tenant_id: str,
    data_dir: Path,
    name: str,
    arguments: dict,
    request: AgentRequest,
):
    if name not in TOOL_MODELS:
        raise ServiceError("unknown_tool", "工具不在允许调用的列表中。", 422)
    params = TOOL_MODELS[name].model_validate(arguments)
    if name == "search_academic_papers":
        return LiteratureService(settings, tenant_id).search(params).model_dump(mode="json")
    if name == "compare_materials":
        return compare_materials(params, settings, tenant_id=tenant_id)
    if name == "get_material_details":
        return (
            MaterialsProjectService(settings).get_details(params.material_id).model_dump(mode="json")
        )
    if name == "search_materials":
        params.limit = min(params.limit, 10)
        result = MaterialsProjectService(settings).search(params)
        QueryStore(data_dir).save(result)
        return result.model_dump(mode="json")
    if name == "get_structure":
        return (
            MaterialsProjectService(settings)
            .get_structure(params.material_id)
            .model_dump(mode="json")
        )
    if name == "search_papers":
        query = SearchRequest(**params.model_dump(), document_id=request.document_id)
        return RagService(settings, tenant_id).search(query).model_dump(mode="json")
    if not request.document_id:
        raise ServiceError("document_required", "请先选择文献以读取实验记录。", 422)
    return (
        DocumentService(data_dir, settings, tenant_id)
        .load_experiments(request.document_id)
        .model_dump(mode="json")
    )
