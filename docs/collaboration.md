# 多角色科研协作

科研助手提供“单 Agent”“自动路由”“多角色协作”三个入口，默认保留单 Agent。
自动路由按所选资料来源和关键词识别跨材料/文献任务；它是可检查的启发式规则，
不是通用科研意图识别模型。单领域任务继续调用现有工具流程，避免强制执行所有角色。

协作流程由 LangGraph 管理：Planner → 材料/文献专家 → Analysis → Reviewer。
Planner 生成恰好两个专家的结构化计划，指定各自目标、工具和依赖。
材料角色只能调用材料查询、详情、结构和快照对比；文献角色只能调用本地证据检索、
实验记录和已配置的 OpenAlex 元数据检索。每个专家独立调用模型决定合法参数，
服务端仍验证工具归属及输入；不存在任意代码或任意 URL 执行能力。

无数据依赖的两个角色并行查询，有依赖时顺序执行并传递真实工具结果。
专家返回结构化证据，不把各自未引用的自然语言草稿当成结论来源。
Analysis 选择来源连续行号，程序复制原文，并拦截未出现在引用中的常见科研量值；
允许与原始数值一致的显示精度舍入。筛选阈值需引用查询参数，不能冒充测量值。
这个量值检查覆盖常用 eV/meV/nm/温度表达式，不等同于完整量纲和科学语义验证。
计算方法也需要明确引文：computed 类型本身不能证明 DFT、第一性原理或 GGA/PBE 等泛函。
该来源检查同时用于单 Agent 与协作流程，防止模型用领域常识补齐工具未返回的方法。

Reviewer 是独立模型步骤，逐条检查样品/属性/数值/单位、计算与实验区分、引用关系、
元数据与全文边界及结论限制。必须对每个 claim_index 恰好检查一次。
被拒绝的结论最多重写一次，再次复核；不会为此重复专家查询。
仍不通过、格式不完整或预算耗尽时返回明确错误，保留候选和阶段状态，不发布未通过的答案。
模型 Reviewer 仍可能漏检，不能代替科研人员独立审核。

## 预算与状态

协作默认最多 10 次模型调用、全局最多 8 次工具调用；模型上限可配置为 5–16。
time_budget_seconds 默认为 240 秒，是模型/工具步骤之间检查的协作时间预算；
已发出的 HTTP 请求受各服务自身超时约束，不保证在截止瞬间取消在途网络调用。
max_steps 约束每个专家的规划循环（协作中最多取 4），不是总模型调用数。
single 模式继续使用原有 max_steps/8 次工具调用限制，不使用协作专属预算字段。

`data/tenants/{tenant_id}/agent_runs/`（默认 `tenants/local/agent_runs/`）保存原子写入的阶段
checkpoint、两个专家的工具记录、Analysis 候选、Reviewer 结果与最终任务。
界面长任务经 `POST /api/v1/jobs/agent` 入队并轮询；也可同步调用 `POST /api/v1/agent/run`。
可通过 GET /api/v1/agent/runs/{run_id}/checkpoint 查看阶段状态，
通过原有任务接口回读最终结果；界面支持输入历史任务 ID 查看答案和复核轨迹。
当前是阶段状态落盘 + 进程内 JobWorker，不提供跨进程自动恢复或远程分布式任务队列。
失败状态中的 candidate 是未经最终通过的调试记录。

```json
{
  "question": "查询 TiO2 计算带隙，并与所选论文的实验带隙比较，说明局限。",
  "document_id": "替换为本机文献 UUID",
  "workflow_mode": "collaborative",
  "required_tools": ["search_materials", "search_papers", "read_experiments"],
  "max_model_calls": 10,
  "time_budget_seconds": 300
}
```

## 验证

tests/test_collaboration.py 在实际 LangGraph 上使用显式合成工具/模型替身，检查并行屏障、
依赖顺序与上下文、工具归属、逐条复核、一次修复、拒绝结果不发布、全局预算、阶段回读与舍入。
这不代表真实科研服务通过。真实验收命令为 `uv run python -m scripts.verify_collaboration`，
执行 MP 查询与论文证据读取，检查筛选条件、3.42 / 3.09 eV、Reviewer 结论、任务/阶段回读，
再由 Edge 验证历史结果与复核界面。报告与截图保存在 data/acceptance/collaboration/。
修复界面脚本时可传入 `--run-id 已完成任务UUID`，回读并重新验证现有真实任务，避免重复模型调用。
单个复杂任务只证明这条流程可用；尚需任务书要求的更多任务、论文与独立质量评测。

图节点和状态机制参考 LangGraph 官方[Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)。
