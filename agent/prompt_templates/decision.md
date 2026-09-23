# 决策模板（Decision）

> 本模板由 decision_loop 在每个决策步填充。占位符使用 `{{TOKEN}}`，渲染时整串替换，
> 不使用 str.format，避免 JSON 花括号冲突。

## 当前游戏状态

{{STATE}}

## 本轮可用操作（只能从中选择）

- 部署：`deploy(operator_id, grid_pos, direction)`
  - 可部署干员（卡牌）：{{AVAILABLE_OPERATORS}}
  - 当前可部署格子：{{DEPLOYABLE_GRIDS}}
  - 费用：{{COST}}；费用不够的干员不要部署。
- 技能：`skill(operator_id, skill_id)`，仅对已部署且技能可开启的干员。
- 撤退：`retreat(operator_id)`，仅对已部署干员。
- 等待：`wait(duration_ms)`，0-60000 毫秒。

## 检索到的知识（注意 evidence 分级，retrieved/inferred 需谨慎）

{{KNOWLEDGE}}

## 上一步反思（若有）

{{REFLECTION}}

## 任务

请下达**本步**应执行的一个或多个动作（按执行顺序放入 plan.actions）。要求：

1. 只选择上面列出的、当前确实可执行的操作；不要虚构干员、格子或技能。
2. 动作要服务于明确目标（回费/拦敌/对空/治疗/应对高防或法抗敌人）。
3. 把每条决策依据写进 reasoning.analysis，并在 knowledge_used 中引用对应来源，
   evidence 分级必须与资料一致。
4. 若信息不足、费用存疑或敌情仅为估算，优先 wait 观察，confidence 不要给满。
5. 仅输出 system.md 规定的 JSON（AgentDecision），不要输出多余文字或注释。
