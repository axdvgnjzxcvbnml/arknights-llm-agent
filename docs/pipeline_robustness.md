# 数据管线健壮性报告

> 审计时间：2026-09-27
> 范围：爬虫 / RAG / 图谱 / SFT 数据准备 四条数据管线

## 一、已有健壮性覆盖

| 管线 | 测试文件 | 用例数 | 覆盖的异常路径 |
| --- | --- | --- | --- |
| 爬虫 | `tests/test_crawler.py` | 41 | HTML 缺字段、JS 对象尾随逗号/单引号/未闭合、boss 特殊布局、名称跨行配对、0 基星级编码 |
| 爬虫 | `tests/test_batch_crawl.py` | - | 断点续爬、限速、分类结构 |
| RAG | `tests/test_chunking_and_rules.py` | - | 干员/敌人/关卡切分、段落合并、克制规则 R1/R2/R3 |
| RAG | `tests/test_build_rag_batch.py` | - | 批量构建、空输入、重复文档 upsert |
| RAG | `tests/test_bm25_retriever.py` | - | BM25 索引构建、空 query、类型过滤 |
| RAG | `tests/test_pipeline_robustness.py` | 5 | 超长文本、控制字符、空段落、最小干员 JSON |
| 图谱 | `tests/test_graph_query.py` | - | 节点查询、子图、克制规则、空图谱 |
| 图谱 | `tests/test_json_load_safe.py` | - | JSON 加载容错（坏文件跳过+日志） |
| SFT | `tests/test_training.py` | - | 数据准备、切分、tokenize |
| SFT | `tests/test_sft_quality_audit.py`（如有） | - | 质量审计边界 |

## 二、发现的脆弱点

### 2.1 爬虫

| 脆弱点 | 严重度 | 状态 | 说明 |
| --- | --- | --- | --- |
| PRTS 页面结构变更 | 高 | ⚠️ 监控 | PRTS Wiki 改版会导致解析器失效；需定期跑 `scripts/crawl_prts.sh` 小样本验证 |
| 编码错误（非 UTF-8） | 中 | ✅ 已处理 | `prts_crawler.py` 用 `response.encoding = response.apparent_encoding` 自动检测 |
| JS 对象极端格式（嵌套未闭合） | 低 | ✅ 已处理 | `_html_utils.extract_js_object` 有括号匹配，未闭合返回 None |
| 限速被封 | 中 | ✅ 已处理 | 1 请求/秒 + 指数退避重试 + 断点续爬 |

### 2.2 RAG

| 脆弱点 | 严重度 | 状态 | 说明 |
| --- | --- | --- | --- |
| 空 JSON 文件 | 低 | ✅ 已处理 | `_load_json_dir` 跳过空文件/坏文件 |
| 超长文本（>10000 字） | 低 | ✅ 已处理 | `_pack_paragraphs` 按 max_chars 硬切，句子边界优先 |
| 非法字符（null/控制字符） | 低 | ✅ 已处理 | 切分器不崩溃，ChromaDB 入库前可清洗 |
| embedding 模型下载失败 | 中 | ✅ 已处理 | `backend=auto` 自动回退 mock 随机向量 |
| BM25 索引构建慢（13511 chunk） | 低 | ✅ 已处理 | 首次构建后缓存到 `data/vector_store/bm25_index/` |

### 2.3 图谱

| 脆弱点 | 严重度 | 状态 | 说明 |
| --- | --- | --- | --- |
| JSON 坏文件 | 中 | ✅ 已处理 | `_load_json_safe` 用 try/except，坏文件记录日志后跳过 |
| 敌人缺 defense/magic_resistance | 低 | ✅ 已处理 | `_to_float` 把 None/空串/非数字转 0.0 |
| 干员缺技能/特性 | 低 | ✅ 已处理 | `_operator_signals` 有默认值兜底 |
| GraphML 83MB 加载慢 | 中 | ✅ 已处理 | 构建时同时输出 pickle（54MB），query_graph 优先读 pickle（1s vs 6s） |
| 克制规则阈值不准 | 中 | ⚠️ 已知 | R1/R2/R3 阈值锚定主线关卡，活动关可能偏差；COUNTERS 恒为 inferred |

### 2.4 SFT 数据准备

| 脆弱点 | 严重度 | 状态 | 说明 |
| --- | --- | --- | --- |
| 非法作业 JSON | 中 | ✅ 已处理 | `load_maa_job` 用 try/except，坏文件跳过 |
| 作业缺 actions | 低 | ✅ 已处理 | `build_examples` 跳过无动作的作业 |
| 非法 action 类型 | 低 | ✅ 已处理 | 只处理 deploy/skill/retreat，其他跳过 |
| 干员名不在 PRTS 白名单 | 低 | ✅ 已处理 | `is_generic_operator` 识别召唤物/装置，分类统计 |
| 黑话/术语不规范 | 低 | ⚠️ 已知 | <1% 占比，保留待 V100 训练后看 eval 表现 |

## 三、加固措施汇总

1. **JSON 加载全链路 try/except**：爬虫/RAG/图谱/SFT 的 JSON 加载都有容错，坏文件不崩溃
2. **类型转换兜底**：`_to_float` 等工具函数把 None/空串/非数字转默认值
3. **embedding 自动回退**：`backend=auto` 在模型不可用时回退 mock
4. **图谱 pickle 加速**：GraphML 83MB → pickle 54MB，加载从 6s 降到 1s
5. **断点续爬**：爬虫支持断点续爬，已爬过的跳过
6. **限速+重试**：爬虫 1 请求/秒 + 指数退避重试
7. **evidence 分级**：推断边（COUNTERS/RECOMMENDS）恒为 inferred，不冒充事实

## 四、后续建议

1. **CI 加数据管线冒烟**：在 CI 里跑 `scripts/crawl_prts.sh --limit 5` 小样本验证爬虫不失效
2. **PRTS 改版监控**：每月跑一次小样本爬取，对比解析成功率
3. **SFT 数据二次净化**：V100 跑完第一版 SFT 后，根据 eval 表现决定是否净化黑话
4. **图谱活动关阈值校准**：如果后续爬活动关，克制规则阈值可能需要分场景调整
