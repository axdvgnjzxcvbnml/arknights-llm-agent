# agent —— LLM Agent 核心（项目的"大脑"，可解释性核心）

慢思考 / 快反应 / 慢快桥接 / 主决策循环，以及 Prompt 模板与结构化输出契约。
**不使用 RL**；决策来自 LLM + RAG + 知识图谱 + MCP 工具。真实模型推理在 V100，
CPU 侧用状态感知的 mock 跑通完整闭环。`import agent` 不拉起 torch/transformers/numpy。

## 模块

| 文件 | 职责 |
|---|---|
| `output_schema.py` | Pydantic 契约：`Reasoning / AgentDecision / BridgeState / FastCommand / Reflection / StepRecord / DecisionLog / KnowledgeBundle / KnowledgeCitation`；动作直接复用 `action.action_space.ActionPlan`（单一事实来源，天然对齐） |
| `slow_thinker.py` | 慢思考：状态+RAG+图谱→`AgentDecision`（reasoning/plan/confidence/knowledge_used）；`SlowThinkerQwen3` 为 `# TODO-V100`，`MockSlowThinker` 为确定性状态感知规则决策；含 Prompt 加载/渲染与自我反思 |
| `fast_reactor.py` | 快反应：慢意图+当前帧→`FastCommand`，对慢思考动作做即时可行性裁剪（费用/手牌/空格/技能就绪），全不可执行退化为短 wait；`FastReactorMiniCPM` 为 `# TODO-V100` |
| `latent_bridge.py` | 慢隐状态→快输入空间投影（避免文字往返延迟）；真实投影 `# TODO-V100`，mock 为确定性伪向量(256)+意图短文本 |
| `decision_loop.py` | 纯 CPU 编排：感知→知识→慢思考→桥接→快反应→执行→反思，逐步入 `StepRecord`；含知识端口（`MockKnowledge`/`RAGGraphKnowledge`）、可演进 mock 战局 `MockPerception`、`build_mock_loop()`、可解释日志渲染/落盘 |
| `config.py` / `configs/agent.yaml` | 模型名/设备/桥接维度/检索条数/循环步数/延迟预算，配置驱动 |
| `prompt_templates/` | system / decision / reasoning / self_reflect 四个模板，`{{TOKEN}}` 占位 |

## 可解释性（每步必产出）

- `reasoning`：结论摘要 + 逐条分析依据 + 候选动作取舍 + 风险；
- `knowledge_used`：引用的每条知识带来源与 evidence 分级（fact / retrieved / inferred /
  cv / estimated / mock），**retrieved/inferred 永不被当成确定事实**；
- `confidence`：估算波次、费用存疑、知识为参考资料时主动下调；
- `reflection`：上一步执行后做 good/risky/bad 自评，问题喂给下一步慢思考。

运行后 `render_decision_log()` 生成带 reasoning/evidence/取舍/反思的可读决策日志，
冒烟落盘到 `results/agent_decision_log.txt`（results 已 gitignore）。

## 慢快分工与延迟

慢思考（Qwen3-8B-Thinking，秒级，强推理+可解释）定"打哪、为什么"；桥接把战略意图投到快
模型输入空间（真实为隐状态，省掉文字往返）；快反应（MiniCPM 级，目标 <150ms）定"这拍能否
做、先做哪个"。VLM 2s 一次、慢思考不到的间隙由 CV+SpawnTracker 与快反应撑住。
V100 相关函数体均 `raise NotImplementedError("TODO-V100: ...")`，文件顶有 `# TODO-V100:`。

## 快速验证（CPU）

```bash
python -m pytest tests/test_agent.py -q   # 契约/边界恒跑，V100 桩验证其明确报错
bash scripts/run_smoke.sh                 # 第 2 段即 Agent 状态->思考->决策->执行闭环
```
