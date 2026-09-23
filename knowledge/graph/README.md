# graph —— 知识图谱（NetworkX）

从 `data/prts_raw/` 已解析 JSON 构建明日方舟实体关系图谱，输出到 `data/graph/`（gitignore）。

## 节点与边

| 边 | 关系 | evidence | 来源 |
|---|---|---|---|
| operator → skill | `HAS_SKILL` 拥有技能 | **fact** | 干员页技能表（结构化） |
| stage → enemy | `CONTAINS_ENEMY` 出场敌人 | **fact** | 关卡敌情表（结构化，带数量/级别） |
| operator → enemy | `COUNTERS` 克制 | **inferred** | 规则推导，带 rule/match_basis/weight |
| stage → operator | `RECOMMENDS` 推荐 | inferred | 关卡敌人经克制规则聚合打分 |

推断边规则（阈值在 `configs/knowledge.yaml` 的 `graph.rules`，按主线关卡敌情数值校准）：

- `R1_high_defense_to_arts`：敌人防御 ≥ 800（重装型）→ 术师（职业克制，weight 1.0）
  或技能描述含"法术伤害/无视防御/真实伤害"的干员（机制克制，weight 0.6）
- `R2_high_resistance_to_physical`：敌人法抗 ≥ 50（高抗型）→ 狙击/近卫（1.0）
- `R3_fast_enemy_to_control`：敌人移速 ≥ 2.0（或描述含高速）→ 技能含减速/束缚/眩晕/停顿/冻结的干员（0.6）

注意：阈值按当前小规模样本（主线 0/1/4/10 章 24 关 + 52 个字典序敌人页，后者偏活动/肉鸽高数值）
校准；语料扩大后需重新校准。碎骨这类"数值检验型"boss 防/抗不达阈值、没有类型弱点，
因此**没有**克制/推荐边——这是规则正确的表现，不是数据缺失。

## 用法

```bash
# 构建（GraphML + build_stats.json）
python -m knowledge.graph.build_graph

# 查询
python -m knowledge.graph.query_graph demo
python -m knowledge.graph.query_graph counter-enemy 碎骨
python -m knowledge.graph.query_graph stage-ops 10-17
python -m knowledge.graph.query_graph operator-skills 能天使
python -m knowledge.graph.query_graph stage-enemies 3-8
python -m knowledge.graph.query_graph heavy-armor
```

代码内调用：

```python
from knowledge.graph.query_graph import GraphQuery
gq = GraphQuery()
gq.operators_for_stage("10-17")     # [{'operator': '艾雅法拉', 'score': 1.0, ...}]
gq.counter_heavy_armor()            # [{'operator': ..., 'score': ..., 'heavy_enemies': [...]}]
```

# TODO-V100: 图谱构建为纯规则+NetworkX，无 GPU 依赖；后续可在 V100 上用 LLM 从攻略文本
# 抽取更精细的 inferred 边（机制联动、具体打法），替换/补充当前数值阈值规则。
