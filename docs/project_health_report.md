# 项目健康检查报告

> 生成时间：2026-09-27
> 范围：全仓库（代码/测试/文档/工程化/性能）

## 一、评分总览

| 维度 | 评分 | 状态 | 关键指标 |
| --- | --- | --- | --- |
| 代码质量 | 黄 | 75/100 | 死代码已清理74处；type hints 79%；错误消息部分不规范 |
| 测试质量 | 绿 | 85/100 | Python 300+测试；前端45测试；异常路径35用例；集成测试14用例 |
| 文档质量 | 绿 | 82/100 | 25+篇文档；术语表已建；一致性审计发现11问题 |
| 工程化 | 黄 | 78/100 | CI 9个job；配置schema验证；日志中间件；依赖有3个未使用 |
| 性能 | 绿 | 88/100 | recommend 7.2s->0.27ms；性能回归脚本；基线已建立 |
| **综合** | **黄** | **81/100** | CPU侧骨架完整，V100待上线 |

## 二、各维度详情

### 2.1 代码质量（黄，75/100）

**优点：**
- 死代码已清理（ruff 修复 72 个未使用 import + 2 个未使用变量）
- 核心模块 type hints 覆盖率 79%（API 层 100%）
- Pydantic 模型覆盖所有数据结构（GameState/ActionPlan/AgentDecision）
- evidence 分级严格（fact/retrieved/inferred/estimated/cv/mock）

**不足：**
- 部分错误消息缺上下文/修复建议（详见 docs/error_message_audit.md）
- derive_counter_rules 对字符串 defense 抛 TypeError（已知脆弱点）
- 3 个依赖未使用（paho-mqtt/grpcio/redis，预留未接入）

### 2.2 测试质量（绿，85/100）

**优点：**
- Python 测试 300+ 用例，覆盖 27+ 测试文件
- 前端 vitest 45 用例（EvidenceBadge/usePolling/utils/client）
- 异常注入测试 35 用例（爬虫/RAG/图谱/SFT 四模块）
- API 集成测试 14 用例（真实 PRTS+图谱端到端）
- 冒烟测试 mock 全链路（截屏->解析->检索->决策->执行）

**不足：**
- 沙箱 4GB 内存，全量 pytest 会 OOM，必须分批跑
- 爬虫解析器的 HTML fixture 测试覆盖不足（需小 HTML fixture）
- 前端 E2E 测试未做（需 Playwright/Cypress）

### 2.3 文档质量（绿，82/100）

**优点：**
- 25+ 篇文档，覆盖架构/API/部署/训练/审计/指南
- 术语表已建（docs/glossary.md，统一 evidence 分级等术语）
- 文档一致性审计已完成（docs/docs_consistency_report.md，11 问题）
- README 全面升级（257 行，含架构图/证据分级/快速开始）

**不足：**
- 部分文档最后更新日期缺失
- 文档间交叉链接不充分
- 过时代码示例需清理

### 2.4 工程化（黄，78/100）

**优点：**
- CI 9 个 job（syntax/smoke/pytest×3/env/frontend-build/frontend-test/coverage）
- 配置 schema 验证脚本（scripts/validate_configs.py，6配置/53字段全通过）
- API 请求日志中间件（方法/路径/状态码/耗时，分级）
- 项目状态一键检查（scripts/project_status.py）
- 性能回归检查（scripts/check_perf_regression.py）

**不足：**
- 3 个依赖未使用（paho-mqtt/grpcio/redis）
- requirements.txt 和 pyproject.toml 依赖重复
- 无 pre-commit hook（ruff/mypy 未在提交前自动跑）

### 2.5 性能（绿，88/100）

**优点：**
- recommend_operators 从 7.2s 降到 0.27ms（预热后，26000 倍提升）
- 图谱加载从 6s 降到 1s（pickle 替代 GraphML）
- MCPKnowledge 6 工具并行调用（总延迟 <300ms）
- 性能基线已建立（docs/benchmark_baseline.md）
- 性能回归脚本已写（scripts/check_perf_regression.py）

**不足：**
- RAG 首次检索 5s（ChromaDB+embedding 冷启动）
- BM25 索引首次构建 30s（13511 chunk）
- V100 真实推理延迟未测（Qwen3-8B 预期 1-2s/步）

## 三、改进优先级

### 高优先级（V100 上线前）
1. V100 环境搭建（PointNet2 编译/Qwen3-8B 部署）
2. SFT 训练跑通（16262 条 train/1818 条 eval）
3. 真实对局端到端验证（模拟器+ADB+Agent 闭环）

### 中优先级（V100 上线后 1 个月内）
4. 前端合并（frontend/ + web/ + web-kb/）
5. API 版本化（/api/v1/ 前缀）
6. 依赖清理（移除未使用的 paho-mqtt/grpcio/redis）
7. type hints 提升到 90%+

### 低优先级（持续改进）
8. 前端 E2E 测试
9. pre-commit hook
10. 文档交叉链接完善
11. 错误消息全面改进

## 四、风险项

| 风险 | 严重度 | 缓解措施 |
| --- | --- | --- |
| V100 PointNet2 编译失败 | 高 | docs/troubleshooting.md 有详细排查指南 |
| SFT 训练 OOM | 中 | QLoRA 4bit + gradient checkpointing，预估 9GB |
| 模拟器 ADB 不稳定 | 中 | MockADBController 已验证接口，真机阶段加重试 |
| 前端合并冲突 | 低 | docs/frontend_merge_plan.md 有详细方案 |
| 数据版权风险 | 低 | PRTS 数据不入库，爬虫脚本可提交 |
