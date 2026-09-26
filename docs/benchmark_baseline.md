# 性能基准 CPU 基线

**测试日期**：2026-09-27
**测试环境**：CPU 沙箱（2 核 EPYC / 4GB / Ubuntu 22.04 / Python 3.12）
**数据规模**：ChromaDB 13511 chunks / BM25 索引 13511 文档 / 知识图谱 ~5000 节点
**用途**：V100 上线后重跑对比，量化 GPU 加速比

---

## 一、RAG 检索延迟（bench_rag.py）

**配置**：3 条 query × 5 次 = 15 样本/模式

| 模式 | P50 (ms) | P95 (ms) | 平均 (ms) | 说明 |
|------|----------|----------|-----------|------|
| 纯向量 | 77.91 | 150.65 | 91.71 | bge-small-zh CPU embedding 是瓶颈 |
| 纯 BM25 | 16.45 | 28.70 | 17.45 | 纯内存关键词匹配，很快 |
| 混合 (RRF) | 111.76 | 116.77 | 109.69 | 向量 + BM25 + RRF 融合 |

**每条 query 延迟（混合检索）**：

| Query | 平均 (ms) | P50 (ms) | P95 (ms) |
|-------|-----------|----------|----------|
| 能天使的技能是什么 | 114.51 | 113.70 | 117.25 |
| 3-8有哪些敌人 | 112.55 | 111.76 | 116.00 |
| 碎骨的属性 | 102.02 | 101.76 | 105.51 |

**分析**：
- 混合检索比纯向量慢约 20ms（BM25 检索 ~17ms + RRF 融合开销）
- V100 上 embedding 迁移到 GPU 后，向量检索预计降至 20-30ms，混合检索预计 40-50ms
- BM25 检索本身极快（~17ms），不是瓶颈

---

## 二、MCP 工具延迟（bench_mcp.py）

**配置**：每个工具 5 次

| 工具 | P50 (ms) | P95 (ms) | 平均 (ms) | 最大 (ms) | 说明 |
|------|----------|----------|-----------|-----------|------|
| query_operator | 0.05 | 0.15 | 0.07 | 0.17 | 纯内存读取 |
| query_skill | 0.02 | 0.04 | 0.02 | 0.04 | 纯内存读取 |
| query_enemy | 0.02 | 0.08 | 0.03 | 0.09 | 纯内存读取 |
| query_stage | 0.02 | 0.07 | 0.03 | 0.07 | 纯内存读取 |
| search_guide | 117.88 | 167.54 | 130.08 | 178.40 | RAG embedding 瓶颈 |
| recommend_operators | 0.01 | 5741.41 | 1435.37 | 7176.77 | ⚠️ 首次调用慢，疑似缓存未命中 |

**分析**：
- 4 个纯内存工具（operator/skill/enemy/stage）延迟 <0.1ms，可忽略
- search_guide 延迟 ~130ms，与 RAG 混合检索一致（embedding 瓶颈）
- **recommend_operators 异常**：首次调用 7.2s，后续调用 <1ms。疑似图谱查询首次遍历全图边后缓存结果。
  V100 上线后需确认是否有同样问题，必要时加启动预热或优化图谱查询算法。

---

## 三、Agent 决策延迟（bench_agent.py）

**配置**：5 局 × 5 步 = 25 步（mock 环境，MockKnowledge）

| 阶段 | P50 (ms) | P95 (ms) | 平均 (ms) | 说明 |
|------|----------|----------|-----------|------|
| perceive | 7.60 | 9.06 | 8.01 | mock 截屏+状态解析 |
| knowledge | 0.00 | 0.00 | 0.00 | MockKnowledge（无真实检索） |
| slow | 0.00 | 0.10 | 0.04 | MockSlowThinker |
| bridge | 0.10 | 0.20 | 0.14 | MockLatentBridge |
| fast | 0.00 | 0.00 | 0.00 | MockFastReactor |
| execute | 0.00 | 0.08 | 0.01 | MockActionExecutor |
| **total** | **7.70** | **9.52** | **8.20** | 端到端单步 |

**局级**：平均 97 ms/局（5 步），P50 64ms，P95 194ms（首局含初始化开销）

**分析**：
- mock 环境下单步延迟 ~8ms，主要是 perceive（mock 截屏 7.6ms）
- 接入 MCPKnowledge 后，knowledge 阶段预计增加 ~80ms（RAG 检索）
- 接入真实慢思考模型后，slow 阶段预计增加 1000-2000ms（Qwen3-8B 推理）
- V100 上端到端单步预计 1.5-2.5 秒（慢思考主导）

---

## 四、视觉解析模块延迟（bench_perception.py）

**配置**：每个模块 20 次（mock 实现）

| 模块 | P50 (ms) | P95 (ms) | 平均 (ms) | 说明 |
|------|----------|----------|-----------|------|
| screen_capture | 2.066 | 2.184 | 2.112 | mock 截屏（真实 ADB 截屏预计 50-100ms） |
| ocr_cost | 0.003 | 0.008 | 0.005 | mock（真实 PaddleOCR 预计 20-50ms） |
| map_parser | 0.000 | 0.001 | 0.000 | mock（真实图像解析预计 10-30ms） |
| detector_yolo (mock) | 0.006 | 0.019 | 0.008 | mock（真实 YOLOv8n GPU 预计 5-15ms） |
| state_parser | 0.005 | 0.011 | 0.007 | 纯 CPU 组装 |
| state_to_text | 0.008 | 0.024 | 0.013 | 纯 CPU 文本生成 |
| vlm_analyzer (mock) | 0.003 | 0.008 | 0.005 | mock（真实 Qwen3-VL 预计 1000-2000ms） |

**快通道合计**：2.13 ms（mock），真实环境预计 100-200ms（ADB 截屏 + OCR + YOLO）

**慢通道（VLM）**：0.01 ms（mock），真实环境预计 1000-2000ms（Qwen3-VL-8B 推理）

---

## 五、V100 对比预期

| 指标 | CPU 基线 | V100 预期 | 加速比 |
|------|---------|-----------|--------|
| RAG 混合检索 | 110ms | 40-50ms | 2-3× |
| search_guide (MCP) | 130ms | 40-50ms | 2-3× |
| Agent 单步 (mock) | 8ms | 8ms (mock) | - |
| Agent 单步 (真实模型) | - | 1500-2500ms | - |
| 快通道 (真实) | - | 100-200ms | - |
| VLM 慢通道 (真实) | - | 1000-2000ms | - |

---

## 六、已知问题与待办

1. ~~**recommend_operators 首次调用慢（7.2s）**~~：**已修复（2026-09-27）**
   - 根因：KnowledgeService 懒加载，首次调用时 `_ensure_data()` 加载 ~1447 个 JSON 文件需 ~6.5s，
     图谱 GraphML 加载需 ~6s（83MB XML）。
   - 修复1：图谱构建时同时输出 pickle 格式（54MB），查询端优先读 pickle（~1s，比 GraphML 快 6 倍）。
   - 修复2：新增 `KnowledgeService.warmup()` 方法，服务启动时预加载数据+图谱（~7.6s），
     避免首次 API 请求冷启动。`api/server.py` 启动时自动调用。
   - 修复后：recommend_operators 预热后 **0.27ms**（从 7200ms 降 26000 倍），
     query_operator/enemy/stage 均 <0.5ms。
   - 注意：RAG 检索器（bge-small-zh + BM25 索引）CPU 加载需 ~75s，
     warmup 默认不加载（`include_retriever=False`），保持懒加载（仅 search_guide 需要）。
2. **embedding CPU 推理是 RAG 瓶颈**：bge-small-zh CPU 推理 ~80ms/query。V100 上迁移到 GPU 后预计降至 20-30ms。
3. **bench_agent 用 MockKnowledge**：knowledge 阶段延迟为 0。接入 MCPKnowledge 后需重跑，预计增加 ~80ms/步。
4. **视觉模块全是 mock**：真实延迟（ADB 截屏、PaddleOCR、YOLOv8n）需 V100/真机上测量。
5. **recommend_operators 返回 0 个干员（3-8）**：疑似图谱 RECOMMENDS 边未构建或 code 不匹配，
   需排查 `build_graph.py` 的 RECOMMENDS 边构建逻辑（独立于性能问题，后续排查）。

---

## 七、运行方式

```bash
# RAG 检索基准
python scripts/bench_rag.py --device cpu --runs 20 --queries 5

# MCP 工具基准
python scripts/bench_mcp.py --device cpu --runs 20

# Agent 决策基准
python scripts/bench_agent.py --device cpu --episodes 10 --steps 8

# 视觉解析基准
python scripts/bench_perception.py --device cpu --runs 50

# V100 上重跑（替换 --device gpu）
python scripts/bench_rag.py --device gpu --runs 20
```

结果 JSON 输出到 `results/benchmarks/`（gitignored）。
