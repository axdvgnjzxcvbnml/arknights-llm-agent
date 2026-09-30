# Stage 3 搜索/规划层设计

> 日期：2026-09-30
> 状态：骨架实现（路径分析+干员匹配+方案生成+方案评分），搜索算法留到私服到位后调优
> 相关文件：`planner/path_analyzer.py`、`planner/operator_matcher.py`、`planner/plan_generator.py`、`planner/plan_scorer.py`

---

## 1. 规划层在系统中的位置

```
游戏截图
    ↓
感知层（CV+OCR+模板匹配）
    ↓
GameState（结构化状态）
    ↓
┌─────────────────────────────────────────┐
│  双通道状态表示（Stage 2）                │
│  文本通道 → LLM 慢思考                    │
│  张量通道 → 规划层（Stage 3，本文件）     │
└─────────────────────────────────────────┘
    ↓
规划层输出：N个候选部署方案 + 评分
    ↓
LLM 决策：从候选方案中选择，给出 reasoning
    ↓
动作执行
```

**规划层与 LLM 的分工**：
- 规划层：做"数值计算"——路径分析、干员匹配、方案枚举、评分排序。输出结构化候选方案。
- LLM：做"语义推理"——理解局势、评估风险、选择方案、给出可解释 reasoning。
- 规划层不做最终决策，只提供候选；LLM 不做暴力搜索，只做选择和解释。

---

## 2. 模块架构

```
planner/
├── __init__.py
├── path_analyzer.py      # 敌人路径分析（BFS）
├── operator_matcher.py   # 干员-拦截点匹配（评分排序）
├── plan_generator.py     # 方案生成（3种策略）
└── plan_scorer.py        # 方案评分（覆盖率+费用+风险）
```

**数据流**：
```
StateTensor
    ↓
path_analyzer.analyze_paths()
    → {paths, interception_points, path_lengths}
    ↓
operator_matcher.match_operators()
    → {拦截点: [候选干员（按评分降序）]}
    ↓
plan_generator.generate_plans()
    → [DeployPlan × 3种策略]
    ↓
plan_scorer.score_all_plans()
    → [PlanScore（按综合评分降序）]
```

---

## 3. 各模块设计

### 3.1 path_analyzer.py — 敌人路径分析

**输入**：StateTensor 的地图张量 + 敌人张量
**输出**：路径格子序列 + 关键拦截点

**核心函数**：
- `bfs_path(start, goal, walkable)`：BFS 求最短路径
- `analyze_paths(state_tensor, entry_points, exit_points)`：分析所有敌人路径
- `path_coverage(interception_points, paths)`：计算拦截点对路径的覆盖率

**骨架实现**：
- 默认入口：左侧中间 `(0, MAP_H//2)`
- 默认出口：右侧中间 `(MAP_W-1, MAP_H//2)`
- 可行走格子：地面格子（高台敌人不走）
- 拦截点：路径上的可部署格子

**TODO-V100**：
- 接入 PRTS 关卡真实路径数据（敌人走固定路径，不是 BFS）
- 多入口/多出口支持
- 敌人类型-路径关联（不同敌人走不同路径）

### 3.2 operator_matcher.py — 干员匹配

**输入**：可用干员（OperatorTensor）+ 敌人类型 + 路径拦截点
**输出**：每个拦截点的候选干员（按评分降序）

**评分维度**（每个干员在每个拦截点的适配度 0~1）：
1. **职业-位置匹配（0.6）**：近战守地面路径、远程放高台、医疗放后排
2. **费用效率（0.2）**：费用越低分越高（20费以上0分）
3. **克制关系（0.2）**：骨架阶段占位，TODO-V100 接入知识图谱 COUNTERS 边

**拦截点分类**：
- `ground_path`：地面路径上的格子（近战位）
- `highland`：高台格子（远程位）
- `backline`：后排格子（医疗位）

**TODO-V100**：
- 接入知识图谱 COUNTERS 边，根据敌人类型计算克制加成
- 干员攻击范围精确计算（不是简单的近战/远程二分）
- 干员技能对路径的影响（如减速、眩晕）

### 3.3 plan_generator.py — 方案生成

**输入**：路径分析 + 干员匹配
**输出**：N个候选方案（每个方案是一组 deploy 动作）

**3种策略**：
1. **greedy（贪心）**：按拦截点评分降序，每点选最优干员
2. **cost_efficient（费用效率）**：按费用升序，预算内部署更多干员
3. **coverage_max（覆盖率优先）**：贪心选择每次覆盖率增益最大的部署

**约束**：
- 不超过 `max_deploys` 个部署（默认4）
- 总费用不超过 `cost_budget`（默认当前费用×1.5）
- 每个干员只用一次
- 每个拦截点只部署一个干员

**TODO-V100**：
- 完整搜索算法（A*/MCTS/启发式）
- 技能/撤退动作纳入方案（当前只生成 deploy）
- 时间序列规划（分波次部署，不是一次性全部署）
- 干员轮换（cost回复后部署新干员）

### 3.4 plan_scorer.py — 方案评分

**输入**：候选方案 + 当前状态
**输出**：每个方案的综合评分（0~1）

**评分维度**（默认权重）：
1. **拦截覆盖率（0.4）**：路径被覆盖的比例
2. **费用效率（0.3）**：费用利用率 + 单位费用覆盖率 + 部署数量
3. **风险控制（0.3）**：高台比例 + 医疗覆盖 + 费用余量 + 部署数量风险

**输出**：
- `total_score`：综合评分 0~1
- `coverage_score`：拦截覆盖率
- `cost_efficiency`：费用效率
- `risk_score`：风险控制（越高风险越低）
- `details`：详细指标

**TODO-V100**：
- 接入地图张量判断部署位置是否高台（当前给中性分0.5）
- 接入干员职业判断医疗覆盖（当前给中性分0.5）
- 敌人类型-风险关联（如Boss关卡需要更高的爆发）
- 学习评分权重（从专家作业中反推最优权重）

---

## 4. 与搜索算法的关系

**当前状态**：骨架实现，用贪心/启发式生成候选方案，不做完整搜索。

**未来演进**：
```
当前（骨架）：3种贪心策略 → 候选方案 → 评分排序
    ↓
短期（私服到位）：A* 搜索，启发式函数=plan_scorer评分
    ↓
中期（数据充足）：MCTS，用 SFT 训练的策略网络指导搜索
    ↓
长期（端到端）：搜索+学习联合优化，AlphaZero 式自我对弈
```

**规划层的接口稳定性**：
- `analyze_paths()`、`match_operators()`、`generate_plans()`、`score_all_plans()` 的输入输出格式稳定
- 搜索算法替换时，只需修改 `plan_generator.py` 内部实现，不影响下游
- LLM 消费的是 `PlanScore.to_dict()` 的结构化输出，与搜索算法无关

---

## 5. 与 LLM 的协作协议

规划层输出给 LLM 的格式：

```json
{
  "candidate_plans": [
    {
      "plan_id": 0,
      "strategy": "greedy: 按拦截点评分降序",
      "total_score": 0.75,
      "coverage": 0.8,
      "cost_efficiency": 0.65,
      "risk": 0.8,
      "total_cost": 11,
      "actions": [
        {"type": "deploy", "operator_idx": 1, "grid_col": 5, "grid_row": 4, "direction": "up"},
        ...
      ]
    },
    ...
  ],
  "recommended_plan_id": 0,
  "state_summary": {"cost": 15, "life": 20, "enemies": 3}
}
```

LLM 的职责：
1. 阅读候选方案的评分和动作
2. 结合局势理解（VLM/文本通道）选择方案或修改方案
3. 输出 reasoning（为什么选这个方案、风险是什么）
4. 输出最终动作序列

---

## 6. 测试覆盖

20个单元测试，覆盖：

| 模块 | 测试数 | 覆盖点 |
|------|--------|--------|
| path_analyzer | 6 | BFS简单路径/不可达/同点/可行走格子/路径分析基本/覆盖率 |
| operator_matcher | 4 | 返回候选/排序/只匹配可用/职业名称映射 |
| plan_generator | 5 | 至少1个方案/动作合法/费用在预算内/策略不同/空匹配不崩溃 |
| plan_scorer | 5 | 评分在0-1/降序/best_plan/空方案不崩溃/自定义权重 |

**测试结果**：20 passed in 0.38s

---

## 7. 已知局限

1. **路径用 BFS 而非真实路径**：明日方舟敌人走固定路径，BFS 只是近似。私服到位后应用 PRTS 真实路径数据。
2. **干员匹配用职业二分**：近战/远程二分，没有精确攻击范围计算。
3. **克制关系占位**：没有接入知识图谱 COUNTERS 边，所有干员给基础克制分。
4. **只生成 deploy 动作**：没有 skill/retreat/wait 动作，方案是静态的一次性部署。
5. **高台/医疗判断占位**：plan_scorer 中高台比例和医疗覆盖给中性分 0.5。
6. **无时间序列**：不考虑分波次部署、cost回复、干员轮换。

这些局限都标注了 `# TODO-V100`，私服到位后逐步完善。
