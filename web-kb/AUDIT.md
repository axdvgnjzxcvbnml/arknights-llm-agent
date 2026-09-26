# web-kb（Kimi 知识库浏览器前端）核对报告

> 范围：仅核对，**未改动前端任何源码**。
> 对照后端：`api/server.py`、`knowledge/graph/build_graph.py`、`knowledge/rag/retriever.py`、`knowledge/mcp_tools/schemas.py`，以及 `data/prts_raw/` 真实爬虫 JSON。
> 环境：Node v22.23.2 / npm 10.9.8。

## 0. 交付与构建

- zip 内顶层目录是 `app/`（另含平级的 `shots/` 5 张参考截图），已落地为 `web-kb/`，截图存 `web-kb/shots/`。
- 文件完整：122 个条目；`src/` 含 3 个页面 `OperatorPage / RagPage / GraphPage` + `api/client.ts` + `types/kb.ts`，shadcn/ui 组件齐全，mock 数据 36 个干员/10 敌人/8 关卡/6 攻略 + `index.json`。
- `npm install`：通过（rc=0）。
- `npm run build`（`tsc -b && vite build`，严格类型）：**通过**，2295 模块，产物 361.8 KB JS / 82.9 KB CSS。
- 当前 `USE_MOCK = true`，纯前端读 `public/mock/`，不连后端即可运行。

---

## 1. 与后端 API 的接口对齐（`USE_MOCK=false` 时才会暴露）

`client.ts` 注释称"接口形状已对齐"，实际切到真实后端会有以下问题（mock 阶段不触发）：

| # | 位置 | 前端现状 | 后端实际 | 影响 |
|---|------|----------|----------|------|
| B1 | `getOperatorDetail` | `GET /api/operators/{name}`（复数） | `GET /api/operator/{name}`（单数） | 404 |
| B2 | `searchRag` | 过滤参数 `type=` | 后端查询参数 `doc_type=` | 类型过滤被静默忽略 |
| B3 | `searchRag` | 期望返回 `RagResult[]` 数组 | 返回 `{found,evidence,hits:[...],note,...}` | 取不到数组，需读 `.hits` |
| B4 | RAG 命中结构 | 嵌套 `{content,score,metadata:{source,type,section,url,evidence}}` | 扁平 `{content,score,source,type,section,url,evidence}` | `RagPage` 读 `r.metadata.*` 全为 undefined |
| B5 | 干员对象 | mock 形 `{meta{...}, traits:{描述}, extra_attrs, skills[].levels[].{lv,...}}` | `OperatorOut` 扁平 `{name,class,star_rating,trait:{branch,desc},skills[].levels[].{level,...}}`（`trait` 单数、`desc` 非`描述`、`level` 非`lv`） | 组件按 mock 形渲染，真实数据不显示 |
| B6 | 图谱 | `buildGraph()` 始终在浏览器用 mock JSON 本地建图 | 后端有 `/api/graph/overview|node|subgraph`、`/api/recommend` | **前端从不调用图谱 API**，看到的只是 mock 子集（非全量 3768 节点/21 万边） |
| B7 | evidence 取值 | `type Evidence = 'fact' \| 'inferred'`；且 mock 把攻略标成 `inferred` | RAG/攻略恒为 `retrieved` | 类型缺 `retrieved`；徽标仅按 fact/非fact 着色所以不崩，但语义错 |
| B8 | score 量纲 | `(score*100).toFixed(1)%`，按 mock bigram 相似度 | 后端 `score=1-cosine距离`（约 0–1） | 数值范围碰巧 0–1、百分比可显示，但语义/数值不可与 mock 直接比较 |

前端目前**只接了 2 个真实接口分支**（search、operator 详情），未消费 enemy/stage/recommend/graph/episode。

---

## 2. R1/R2/R3 克制规则漂移（`client.ts:buildGraph` vs `build_graph.py`）

**一致的部分**（核对无误）：阈值 `800 / 50 / 2.0` 与 `configs/knowledge.yaml` 完全一致；
关键词表完全一致（法术 `法术伤害/无视防御/真实伤害`、物理职业 `狙击/近卫`、控制 `减速/束缚/眩晕/停顿/冻结`）；
权重一致（R1：术师职业 1.0、技能关键词 0.6；R2：1.0；R3：0.6）；取敌人"最强级别"`levels[-1].data` 的口径一致。

**漂移点**：

- **C1 关键词文本范围不同（会多出克制边）**：前端 `operatorSkillBlob` 把干员**特性描述** `op.traits.描述` 也拼进关键词文本；后端 `_operator_signals` 只取技能 `type` + 各技能等级 `desc`，**不含特性**。前端可能因特性措辞额外触发 R1/R3。
- **C2 R3"高速"判定缺失（会少边）**：后端 R3 触发条件是 `移速≥2.0` **或** 敌人 `描述/特性` 含"高速"二字；前端只判 `speed≥2.0`，漏掉移速缺失但文案写"高速"的敌人。
- **C3 节点身份口径不同**：前端干员用 `meta.name`、敌人用 `e.name`；后端已统一为**页面标题（文件名）**以避免异格/多形态错误合并（如 `能天使` 与 `新约能天使`、`X` 与 `X(DC3)`）。mock 无重名所以暂不暴露，换真实数据会错。
- **C4 敌人覆盖不同**：后端会为"只出现在关卡敌情表、无独立敌人页"的敌人补建节点；前端只为敌人 JSON 建节点，关卡表里对不上的行会被静默丢弃（`CONTAINS_ENEMY` 少边）。
- **C5 RECOMMENDS 打分语义不同（最大差异）**：
  - 后端：每个(关卡,干员)对每个敌人取其在 R1/R2/R3 中的**最高权重**，再对**不同敌人求和**（`score=Σbest`，`support=命中敌人数`，附 `matched_enemies/matched_rules`），并把关卡行名解析到页面身份、对重复行去重；
  - 前端：遍历每条 COUNTERS 边累加权重，最后输出**平均值** `Σw/n`，且按原始显示名匹配、重复行会重复计数。
  - 结果：两边 RECOMMENDS 的**数值和排序都可能不同**。
- **C6 边/节点字段名不同**：后端 COUNTERS 用 `reason/match_basis/weight`，前端用 `detail/weight/rule`；后端 RECOMMENDS 用 `score/support/matched_enemies/matched_rules`，前端只有 `weight/detail`。节点 id 前缀也不同：前端 `op:/sk:/en:/st:`，后端 `operator:/skill:/enemy:/stage:`。（因 B6 前端不调图谱 API，暂不直接冲突。）
- **C7 mock 数据 schema ≠ 真实爬虫 schema**：mock 关卡敌情在 `normal.敌情[]`（`级别` 是"领袖/普通/精英"文案），真实数据在**顶层** `enemies[]`（`级别` 是 "0"，另有 `地位`，数值在 `防御力/移动速度/...`）；`消耗理智` 真实为 `作战消耗`；干员 mock 用 `traits`(复数)/`lv`，真实用 `trait`(单数)/`level`。mock 由 `scripts/gen_mock.py` 自定义生成，自洽但不是 `prts_raw` 真实结构，因此 types/kb.ts 顶部"与 crawler/rag/graph 对齐"的注释对真实数据不成立。

---

## 3. 建议（本次不改，待确认）

1. **最优解**：前端删除本地 `buildGraph`，改为消费后端 `/api/graph/*` 与 `/api/recommend`，可一次性消除 C1–C6 全部规则漂移（规则单一来源在后端）。
2. 若保留本地建图，则至少同步 C1（去掉特性文本）、C2（补"高速"文案）、C3（页面标题身份）、C5（改 Σbest + support），并把节点 id/字段名对齐后端。
3. 切真实后端前需加一层 **adapter**：修 B1–B5（路径、`doc_type`、读 `.hits`、扁平化命中、`OperatorOut` 映射），并把 `Evidence` 扩为含 `retrieved`（B7）。
4. C7 需要决策：mock 是否改成真实 `prts_raw` schema（推荐改，否则 mock→真实的切换永远有隐藏断裂）。

> 优先级：B1–B5 + B7 是"能不能连真后端"的硬门槛；C1/C2/C3/C5 是"图谱结论是否与后端一致"的正确性问题。

---

# 4. 方案 A 落地记录（2026-09-26，已改前端）

用户拍板**方案 A：前端只消费后端 API**。本地 `buildGraph` 已删除，规则单一来源在后端。

## 4.1 改造内容

- `src/api/client.ts` 重写为纯 API 客户端：
  - `USE_MOCK`（可用 `VITE_USE_MOCK=false` 覆盖）。`true` 读 `public/mock/**` 接口夹具；`false` 调真实 `/api/*`。两模式 TS 返回类型完全一致。
  - `getOperatorDetail → GET /api/operator/{name}`（**B1 修复**，单数）。
  - `searchRag → GET /api/search?q&k&doc_type`（**B2 修复**），返回 `SearchResponse`、读 `.hits`（**B3 修复**），命中为扁平 `RagHit{content,score,source,type,section,url,evidence}`（**B4 修复**）。
  - 删除 `buildGraph/chunksOf` 等本地逻辑（**B6/C1–C6 从根上消除**）；新增 `getStageSubgraph→/api/graph/subgraph/{stage}`、`getRecommend→/api/recommend/{stage}`、`getNodeDetail→/api/graph/node/{id}`。
  - score 量纲统一 0–1（真实 `1-cosine距离`；mock bigram 归一化），前端统一 `×100%`（**B8 一致**）。
- `src/types/kb.ts` 重写为后端响应类型：`OperatorDetail`（扁平、`class` 别名、`trait{branch,desc,branch_info}`、`levels[].level`）、`RagHit/SearchResponse`、`SubgraphResponse/GraphNodeApi/SubgraphEdge`、`NodeDetailResponse/NodeNeighbor`、`RecommendResponse/RecommendedOperator`；`EvidenceLevel` 增 `retrieved`（**B5/B7 修复**）。
- 页面：
  - `RagPage` 消费 `.hits` 扁平字段；evidence 三档着色 fact/retrieved/inferred，并展示后端 `note`。
  - `OperatorPage` 用 `OperatorOut` 字段渲染（去掉后端不提供的 obtain/growth）；右侧克制敌人/推荐关卡改读 `/api/graph/node` 邻居（COUNTERS-out / RECOMMENDS-in），恒标 inferred。
  - `GraphPage` 改为**关卡驱动**：关卡选择 → 并行拉 subgraph + recommend，d3 展示关卡子图（stage/enemy/operator），侧栏展示推荐干员（score/support/matched_enemies/rules + inferred note）与节点邻居。
- `vite.config.ts` 加 `/api` → `http://127.0.0.1:8000` 代理（`ARK_API_TARGET` 可覆盖）。

## 4.2 mock 数据按真实 schema 重建（C7 修复）

- 新增 `mock_src/`（**虚构文本、无 PRTS 版权内容**），但结构严格对齐真实爬虫：`trait` 单数、`skills[].levels[].level`、顶层 `enemies[]`、级别 `"0"`+`地位`、`作战消耗`。数据集刻意覆盖 R1（重装组长 防1000→术师阿米娅 1.0）、R2（术抗卫士 抗60→狙击能天使/克洛丝 1.0）、R3（冲锋兵 速2.2→辅助梓兰 减速 0.6），并含无类型弱点的 Boss 碎骨（**验证规则不无中生有**）。
- `scripts/gen_mock.py` 重写：**直接复用后端真实代码**生成 `public/mock/**` 夹具——真实 `build_graph`（阈值取自 `configs/knowledge.yaml`）建图、`NetworkXGraphProvider` 出 overview/node/subgraph、`KnowledgeService`+MCP 工具出 operator/stage/recommend，`model_dump(by_alias=True)` 落盘，且每件夹具用 `knowledge/mcp_tools/schemas` 的 Pydantic 模型反查校验。
  → mock 与真实不仅形状一致，**克制结论也由同一份后端代码产生**，C1–C6 不可能再漂移。
- 旧 `public/mock/prts_raw/`（自造 schema）已整体删除。

## 4.3 验证

- `npm run build`（`tsc -b && vite build` 严格类型）：**通过**，2295 模块，产物 358.7 KB JS / 82.9 KB CSS。
- 生产包静态服务抽查：`mock/catalog.json`、含中文名的 `mock/operator/阿米娅.json`、`mock/node/operator_阿米娅.json` 均 200。
- **真实后端联调**（`uvicorn api.server:app` + 全量本地数据，临时 curl，未提交数据）：

| 接口 | 结果 |
|------|------|
| `GET /api/operator/能天使` | 200，`class=狙击 star=6 trait{branch,desc,branch_info} levels[].level` 与 TS 类型一致 |
| `GET /api/search?q=碎骨` | evidence=`retrieved`，hits 扁平字段一致；`doc_type=enemy` 过滤生效 |
| 未命中干员 | 200 + `found:false`（前端安全转"未找到"） |
| `GET /api/graph/subgraph/1-11` | 200，7 敌人 + 50 推荐（`operators_truncated=true` 被页面识别） |
| `GET /api/recommend/1-11` | 200，`RecommendedOperator` 八字段（class/star/score/support/matched_enemies/matched_rules/evidence）一致 |

## 4.4 已知差异 / 后续建议（真实模式才出现，非阻断）

> **【待办 · 2026-09-26 用户拍板】合并后统一处理：node 邻居查询改分组配额，另加反向"推荐关卡"接口。**
> 时机：等两个 web（web-kb + Qwen 的 web/）合并、总览 Dashboard 做完后统一处理；当前不改后端，避免提前引入复杂度。
> 背景：`/api/graph/node/{id}` 邻居硬上限 200、且先 out 后 in，热门干员（如能天使 773 邻居、197 COUNTERS 出边占满 200）的 RECOMMENDS 入边被截断，真实模式右侧"推荐关卡"为空；mock 小图正常。正确修法是 ①按 (relation,direction) 分组各给配额，②新增按干员反查"推荐关卡"的接口——两者都要。

1. **高知名度干员的"推荐关卡"可能为空**：见上方待办（节点邻居截断）。本批不改后端。
2. **默认演示关卡 3-8 / 1-7 在全量图上 0 条 RECOMMENDS**：阈值 800/50/2.0 下这些关卡敌人未触发规则（前端正确显示空态 + note）。全量数据中有推荐的如 `1-11`。mock 夹具的 3-8/1-7 因虚构数值特意触发规则，便于离线演示——两种都是后端真实输出，差异仅在数据。
3. 后端无"列出全部干员/关卡"接口，前端选择器使用内置 `FEATURED_*` 清单（mock 下用 `catalog.json` 补标签）。需要全量浏览器时建议后端补 `/api/catalog`。

## 4.5 状态小结

- B1–B8：**全部修复**。
- C1–C6：删除前端建图后**结构性消除**；mock 夹具由后端真实代码生成，结论可复现。
- C7：mock 改为真实爬虫 schema，且夹具经 Pydantic 校验。
- 版权红线：`mock_src` 与 `public/mock` 全为虚构示例；`node_modules/`、`dist/`、`.mockbuild/` 已 gitignore；真实 `data/` 未进入前端目录。
