# prompt_templates —— Prompt 模板

| 模板 | 作用 |
|---|---|
| `system.md` | AI 身份（方舟参谋）、职责、证据分级铁律、AgentDecision JSON 输出格式与字段约束 |
| `decision.md` | 决策模板：当前状态 / 可用操作（手牌·空格·费用）/ 检索知识 / 上一步反思 / 输出要求 |
| `reasoning.md` | 慢思考"先分析、再决策"的 7 步顺序（读状态→判敌情→对知识→定目标→评候选→查风险→决策） |
| `self_reflect.md` | 上一步决策复盘，产出 Reflection（good/risky/bad + 问题 + 下一步修正） |

## 约定

- 占位符统一用 `{{TOKEN}}` 形式，由 `slow_thinker.render_template` **整串替换**；
  不使用 `str.format`，因此模板里的 JSON 花括号示例不会被破坏。
- 四个模板都强调 evidence 分级（fact/retrieved/inferred/cv/estimated/mock），
  要求模型照抄来源分级、不得把 retrieved/inferred 升级成事实。
- V100 真实推理时，`SlowThinkerQwen3.build_prompt()` 会加载 system+decision+reasoning
  组装成 messages；self_reflect 供 `reflect()` 使用。
