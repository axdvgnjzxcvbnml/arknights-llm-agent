# 文档一致性审计报告

**审计日期**：2026-09-27
**审计范围**：`docs/` 下全部 15 个文档（共 2888 行）
**审计方法**：逐文档阅读，对照实际代码（路由、配置、模块状态、测试数）核对
**严重程度**：🔴 高（事实错误/内部矛盾）｜🟡 中（过时/缺失）｜🟢 低（格式/小问题）

---

## 一、问题总览

| # | 文档 | 严重度 | 问题 |
|---|------|--------|------|
| 1 | `v100_handoff.md` | 🔴 | 内部矛盾：第51行说 torch_dtype 未改，第151行说已修正；实际已是 float16 |
| 2 | `v100_handoff.md` | 🔴 | 第207行 D3 待办项"torch_dtype 改 float16"实际已完成 |
| 3 | `benchmark_baseline.md` | 🔴 | MCP延迟表格 recommend_operators 仍是修复前 7.2s，已知问题章节已标记修复为 0.27ms |
| 4 | `project_plan.md` | 🟡 | 只更新到第15批，缺少第16-22批（Dashboard API/MCPKnowledge/RAG混合检索/性能基准等） |
| 5 | `architecture.md` | 🟡 | 模块状态表只到第十五批；chart_reader 标注"⏳骨架"实际已补完真实实现 |
| 6 | `experiment_log.md` | 🟡 | 最后记录 2026-09-24（第八批起点），之后14批无实验记录 |
| 7 | `coverage_report.md` | 🟡 | 覆盖率数字可能过时（写报告后测试从~300增至482） |
| 8 | `docs/README.md` | 🟡 | 只列6个文档，实际15个；引用不存在的 setup.md |
| 9 | `setup.md` | 🟡 | 被 docs/README.md 引用但文件不存在 |
| 10 | `api.md` | 🟢 | `/api/episode/{id}` 参数名与代码 `{episode_id}` 不一致（不影响功能） |
| 11 | `project_plan.md` | 🟢 | 第2批说 RAG 923 chunk，实际 13511 chunk；第15批说263测试，实际482 |

---

## 二、逐文档详细问题

### 1. `v100_handoff.md`（🔴 高）

**问题1：内部矛盾——torch_dtype 状态**
- 第51行：`⚠️ model.torch_dtype: bfloat16 需改为 float16（当前注释已标注，但值未改）`
- 第151行：`model.torch_dtype | float16 | ✅ 已修正 | 原 bfloat16...`
- 实际 `configs/training.yaml:8`：`torch_dtype: float16`（已改）
- **结论**：第51行的警告已过时，应删除或标记为"已修正"

**问题2：D3 待办项已完成**
- 第207行：`D3 | configs/training.yaml 的 model.torch_dtype 改 float16 | 高 | 当前是 bfloat16...`
- 实际已是 float16
- **结论**：D3 应标记为已完成，或从待办清单移除

### 2. `benchmark_baseline.md`（🔴 高）

**问题：MCP 工具延迟表格与已知问题章节矛盾**
- 第46行表格：`recommend_operators | 0.01 | 5741.41 | 1435.37 | 7176.77 | ⚠️ 首次调用慢`
- 第115行已知问题：`~~recommend_operators 首次调用慢（7.2s）~~：已修复（2026-09-27）...修复后 0.27ms`
- **结论**：表格是修复前的基线数据，应在表格上方注明"以下为修复前基线（2026-09-27前），修复后数据见已知问题章节"，或新增修复后数据列

### 3. `project_plan.md`（🟡 中）

**问题1：缺少第16-22批**
- 当前路线图只到第15批（视频分类+源石台账+菜单骨架+培养决策）
- 缺少的批次：
  - 第16批：Dashboard 9 接口（/api/health扩展、resources、tasks、live、training）
  - 第17批：LiveState 线程安全修复 + v100_handoff 文档
  - 第18批：前端合并方案 + 爬虫单测41用例
  - 第19批：MCP工具与Agent联通（MCPKnowledge）+ 活动关卡分类 + SFT预tokenize
  - 第20批：MCPKnowledge延迟测量 + 端到端闭环测试 + SFT训练配置核对
  - 第21批：RAG混合检索（BM25+向量RRF）+ 覆盖率补齐 + 快反应增强 + 性能基准套件
  - 第22批：recommend_operators性能修复 + chart_reader VLM实现 + MAA决策模式统计
- **结论**：应在阶段0表格中追加第16-22批

**问题2：数字过时**
- 第2批："RAG（bge-small-zh + ChromaDB，923 chunk）"→ 实际 13511 chunk（全量重建后）
- 第15批："全量 263 passed/2 skipped"→ 实际 482 测试函数（27个测试文件）
- **结论**：更新数字

### 4. `architecture.md`（🟡 中）

**问题1：模块状态表只到第十五批**
- 第309行开始是"第十四批：视频提取骨架"
- 第324行开始是"第十五批新增：源石台账/菜单骨架/培养决策"
- 缺少第十六批及以后的模块状态（Dashboard API、MCPKnowledge、RAG混合检索、性能基准、recommend_operators修复、chart_reader VLM实现等）

**问题2：chart_reader 状态过时**
- 第316行：`video_extract/chart_reader.py | ⏳ VLMChartReader 骨架 # TODO-V100`
- 实际：第二十二批已补完 `_load_model()` + `read_chart()` 真实实现（含 markdown fence 剥离、示例字面量校验）
- **结论**：应更新为"✅ 真实实现已补完（V100上运行，含fence剥离+示例校验）"

**问题3：MCPKnowledge 延迟数据可能需更新**
- 第81行："MCPKnowledge 知识检索 ≤100ms（实测平均77ms/P95 92ms）"
- 这是第二十一批的数据，recommend_operators 的7.2s问题在第二十二批修复
- 修复后 recommend_operators 预热后 0.27ms，整体延迟应更低
- **结论**：可补充修复后数据

### 5. `experiment_log.md`（🟡 中）

**问题：实验记录停留在 2026-09-24**
- 最后一条："2026-09-24 ｜ Mock 闭环基线（CPU，第八批起点）"
- 之后14个批次（第九~二十二批）没有实验记录
- 特别是应该记录的实验：
  - RAG 混合检索 vs 纯向量的检索质量对比（5条query）
  - MCPKnowledge 延迟测量（77ms平均）
  - recommend_operators 性能修复前后对比（7.2s → 0.27ms）
  - 性能基准套件 CPU 基线数据
  - MAA 作业决策模式统计结果
- **结论**：应补充关键实验记录（至少补充 RAG 混合检索、性能修复、MAA 统计三条）

### 6. `coverage_report.md`（🟡 中）

**问题：覆盖率数字可能过时**
- 报告写于第二十二批前半（RAG混合检索+覆盖率补齐时）
- 之后又新增了 chart_reader 19个测试、MCPKnowledge相关测试等
- 当前总测试函数 482 个（27个测试文件），报告中可能引用的是~300时的数据
- **结论**：应重新跑覆盖率统计，更新数字

### 7. `docs/README.md`（🟡 中）

**问题1：文档列表不完整**
- 只列了6个文档（architecture/setup/v100_checklist/troubleshooting/experiment_log/project_plan）
- 实际有15个文档，缺少：api.md、benchmark_baseline.md、coverage_report.md、dashboard_design.md、frontend_merge_plan.md、maa_decision_patterns.md、sft_data_quality.md、v100_handoff.md、docs_consistency_report.md（本报告）

**问题2：引用不存在的 setup.md**
- 列表中有 `setup.md | 环境搭建`，但 `docs/setup.md` 文件不存在
- **结论**：要么创建 setup.md，要么从列表中移除

### 8. `setup.md`（🟡 中）

**问题：文件不存在但被引用**
- `docs/README.md` 引用了 setup.md
- 实际环境搭建内容可能散落在 README.md、v100_checklist.md、v100_handoff.md 中
- **结论**：应创建 setup.md（汇总 CPU 侧环境搭建步骤），或从 docs/README.md 移除引用

### 9. `api.md`（🟢 低）

**问题：参数名不一致**
- 文档：`GET /api/episode/{id}`
- 代码：`@app.get("/api/episode/{episode_id}")`
- 不影响功能（FastAPI 按位置匹配），但文档应与代码一致
- **结论**：统一为 `{episode_id}`

### 10. 已确认最新的文档（无需修改）

| 文档 | 状态 |
|------|------|
| `api.md` | 17个路由全部对齐，仅参数名小问题 |
| `sft_data_quality.md` | 样本数18080正确，黑话<1%决定已记录 |
| `dashboard_design.md` | 技术栈已更新为 React 19 + Vite 7 |
| `frontend_merge_plan.md` | 方案文档，等 Qwen web/ 到齐后执行 |
| `maa_decision_patterns.md` | 刚完成修正（干员/召唤物分类+时间维度说明） |
| `troubleshooting.md` | 4个大章节，内容较新 |
| `v100_checklist.md` | dtype=float16 正确，PointNet2 P0 标注正确 |

---

## 三、修复建议优先级

### 立即修复（🔴 事实错误/内部矛盾）

1. `v100_handoff.md`：删除第51行过时警告，D3 标记为已完成
2. `benchmark_baseline.md`：MCP 表格注明"修复前基线"，或新增修复后数据

### 建议修复（🟡 过时/缺失）

3. `project_plan.md`：追加第16-22批，更新 RAG chunk 数和测试数
4. `architecture.md`：追加第十六批后模块状态，更新 chart_reader 状态
5. `experiment_log.md`：补充 RAG 混合检索、性能修复、MAA 统计三条实验记录
6. `docs/README.md`：更新文档列表为15个，处理 setup.md 引用
7. `coverage_report.md`：重新跑覆盖率，更新数字
8. `setup.md`：创建或移除引用

### 可选修复（🟢 格式/小问题）

9. `api.md`：统一参数名为 `{episode_id}`

---

## 四、审计方法说明

- 文档清单：`ls docs/*.md`（15个文件，2888行）
- 代码对照：`grep` 实际路由/配置/模块状态，与文档声明逐一比对
- 测试数：`grep -rc "def test_" tests/test_*.py`（482个测试函数，27个文件）
- 配置值：直接读取 `configs/*.yaml` 确认 dtype 等关键字段
- 未做：逐字校对所有代码示例（工作量过大，仅核对关键声明）
