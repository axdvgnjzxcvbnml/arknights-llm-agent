# arknights-llm-agent

> 能看、能想、能打、能解释的明日方舟 AI Agent —— LLM Agent + RAG + MCP，不用 RL。

[![CI](https://github.com/axdvgnjzxcvbnml/arknights-llm-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/axdvgnjzxcvbnml/arknights-llm-agent/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](./pyproject.toml)

## 一句话

用 LLM Agent 看懂明日方舟游戏画面、查 PRTS Wiki 攻略、做部署决策、输出可读的思考过程——**每一步决策都带 reasoning 和知识引用**。

## 核心卖点

- **可解释性**：每次决策输出 `reasoning`（思考过程）+ `knowledge_used`（引用来源），evidence 分 7 级（fact/retrieved/inferred/estimated/cv/vlm/mock），推断和事实严格区分。
- **慢快双脑**：慢思考（Qwen3-8B-Thinking，1-2s）负责战略决策，快反应（MiniCPM3-4B，<150ms）负责即时操作，latent bridge 预留隐藏态投影接口。
- **CV+VLM 双通道视觉**：快通道 YOLOv8+OCR（<50ms）负责实时状态，慢通道 VLM（2s/次）负责局势理解和战略建议。
- **知识库三件套**：RAG 混合检索（向量+BM25+RRF 融合）+ NetworkX 知识图谱（3768 节点/219593 边）+ MCP 工具集（6 个标准工具）。
- **CPU 侧完整可跑**：mock 全链路冒烟测试不依赖 GPU/模拟器/真实数据，`git clone` 后 3 分钟跑通。

## 快速开始

### 环境要求

- Python >= 3.8（CI 强制 3.8 语法兼容；开发建议 3.10+）
- 冒烟测试**不需要** GPU、模拟器、PRTS 数据、网络

### 三步跑通 mock 全链路

```bash
git clone https://github.com/axdvgnjzxcvbnml/arknights-llm-agent.git
cd arknights-llm-agent
pip install numpy pydantic pyyaml rich pytest   # 冒烟测试最小依赖
bash scripts/run_smoke.sh                        # 截屏→解析→检索→决策→执行→视频提取
```

预期输出：`[run_smoke] 全部冒烟通过`。

### 完整开发环境

```bash
pip install -e .          # 安装全部依赖（含 torch/transformers/chromadb 等）
python -m pytest tests -q # 全量单元测试（缺数据/GPU 的用例自动 skip）
cd frontend && npm install && npm run build  # 前端构建
```

## 架构总览

```
游戏画面 (ADB 截屏)
    │
    ▼
┌─────────────────────────────────────────────────┐
│  感知层 perception/                               │
│  ┌──────────────┐    ┌──────────────────────┐   │
│  │ 快通道 CV    │    │ 慢通道 VLM            │   │
│  │ YOLOv8+OCR   │    │ Qwen3-VL (2s/次)     │   │
│  │ <50ms         │    │ 局势理解+战略建议     │   │
│  └──────┬───────┘    └──────────┬───────────┘   │
│         └──────────┬─────────────┘               │
│                    ▼                               │
│           结构化 GameState + state_to_text        │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  知识层 knowledge/                                │
│  RAG(向量+BM25+RRF) ←→ 知识图谱 ←→ MCP 工具    │
│  evidence: fact/retrieved/inferred/estimated     │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  决策层 agent/                                    │
│  慢思考 Qwen3-8B-Thinking (1-2s)                │
│    → reasoning + action + confidence              │
│  快反应 MiniCPM3-4B (<150ms)                     │
│    → 具体操作序列                                  │
│  latent_bridge: 慢→快隐藏态投影 (预留)           │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│  执行层 action/ → ADB → MuMu 模拟器              │
│  部署/技能/撤退/等待                              │
└─────────────────────────────────────────────────┘
```

**证据分级（7 档）**：

| 级别 | 含义 | 边框 |
| --- | --- | --- |
| `fact` | PRTS/官方事实 | 实线 |
| `cv` | 视觉检测确认 | 实线 |
| `retrieved` | RAG 检索到的外部观点 | 虚线 |
| `inferred` | 规则/模型推断 | 虚线 |
| `estimated` | 估算值（如波次时间） | 虚线 |
| `vlm` | VLM 观点 | 实线（语义色） |
| `mock` | Mock 数据 | 实线（灰色） |

## 项目结构

```
arknights-llm-agent/
├── agent/                  # LLM Agent 核心
│   ├── decision_loop.py    # 主决策循环（截屏→解析→检索→决策→执行→记录）
│   ├── slow_thinker.py     # 慢思考（Qwen3-8B-Thinking，mock+TODO-V100）
│   ├── fast_reactor.py     # 快反应（MiniCPM3-4B，规则引擎+TODO-V100）
│   ├── latent_bridge.py    # 慢快桥接（预留 hidden_state 投影接口）
│   ├── knowledge_port.py   # MCP 知识端口（串行→并行，6工具<10ms）
│   ├── output_schema.py    # 结构化输出（Pydantic：reasoning/action/confidence）
│   └── prompt_templates/   # Prompt 模板（system/decision/reasoning/self_reflect）
├── knowledge/              # 知识库
│   ├── crawler/            # PRTS Wiki 爬虫（5516 页面：干员/敌人/关卡/攻略）
│   ├── rag/                # RAG 混合检索（bge-small-zh + ChromaDB + BM25 + RRF）
│   ├── graph/              # 知识图谱（NetworkX，3768 节点/219593 边，pickle 加速）
│   ├── mcp_tools/          # MCP 工具集（6 工具：operator/skill/enemy/stage/search/recommend）
│   └── source_stone_tracker.py  # 源石获取策略（三档：立即可拿/短期/长期）
├── perception/             # 视觉解析（CV+VLM 双通道）
│   ├── screen_capture.py   # ADB 截屏（MuMu 127.0.0.1:7555）
│   ├── state_parser.py     # 游戏状态解析（含 SpawnTracker 波次推算）
│   ├── detector_yolo.py    # YOLOv8 检测（骨架+confirm_spawn 接口）
│   ├── ocr_cost.py         # PaddleOCR 费用识别（两帧一致性容错）
│   ├── map_parser.py       # 地图格子解析（缓存布局）
│   ├── vlm_analyzer.py     # VLM 慢通道（骨架+TODO-V100）
│   └── state_to_text.py    # 状态→自然语言（喂给 LLM，evidence 分级桶）
├── action/                 # 动作执行
│   ├── adb_controller.py   # ADB 封装（点击/拖拽/截屏/按键，Mock 记录操作）
│   ├── action_space.py     # 动作空间（部署/技能/撤退/等待，Pydantic 严格校验）
│   └── action_executor.py  # 动作执行器（批量执行+失败不中断+等待间隔）
├── env/                    # 环境封装
│   ├── arknights_env.py    # Gym 风格（reset/step/get_state/is_done，依赖注入）
│   ├── mock_env.py         # Mock 环境（10 步通关/3 步失败）
│   ├── reward.py           # 奖励计算（评估用，非 RL 训练）
│   └── episode_store.py    # 对局日志存储（一局一 JSON，API 读取）
├── api/                    # FastAPI 服务端（17 路由 + WebSocket）
│   ├── server.py           # 知识工具/对局/图谱/资源/任务/实时/训练 接口
│   └── live_state.py       # 实时对局帧 pub/sub（线程安全，call_soon_threadsafe）
├── strategy/               # 策略层
│   └── operator_development.py  # 干员培养优先级决策（强度榜逻辑，占位规则）
├── video_extract/          # 视频素材提取（血狼破军等 UP 主）
│   ├── downloader.py       # yt-dlp 下载（分类过滤：明日方舟/终末地/其他）
│   ├── frame_extractor.py  # ffmpeg 抽帧（固定间隔+场景切换）
│   ├── transcriber.py      # ASR 转写（Whisper，骨架+TODO-V100）
│   ├── chart_reader.py     # VLM 读图表（完整实现：Qwen3-VL，含示例字面量防护+markdown fence 剥离）
│   ├── aligner.py          # 时间轴对齐（口播↔画面就近匹配）
│   └── structurer.py       # SFT 格式结构化（问答对+BV+时间戳来源）
├── training/               # V100 训练
│   ├── sft_data_prep.py    # SFT 数据准备（CPU 真实：18080 条，关卡维度切分）
│   ├── pre_tokenize.py     # 预 tokenize（CPU：417 万 token，V100 直接加载）
│   ├── sft_quality_audit.py # SFT 数据质量审计
│   ├── sft_train.py        # SFT 微调脚本（QLoRA+LoRA+cosine warmup，TODO-V100）
│   └── dpo_train.py        # DPO 偏好训练（骨架+TODO-V100）
├── frontend/               # 统一前端（React 19 + Vite 7 + Tailwind 3.4）
│   ├── Dashboard 总览（6 模块）/ 实时对局 / 回放 / 资源 / 训练
│   └── 45 个 vitest 单元测试
├── web-kb/                 # 知识库前端（Kimi，三页：RAG/图谱/干员）
├── configs/                # 配置文件（7 个 yaml，路径/模型名/超参不硬编码）
├── scripts/                # 工具脚本（含 V100 上线五步 + 4 个基准脚本）
├── tests/                  # 单元测试（27 文件/496 测试函数，含 API 集成测试）
├── docs/                   # 文档（20+ 篇，见下方索引）
└── .github/workflows/      # CI（9 个 job：语法/冒烟/3组pytest/环境/前端构建/前端测试/覆盖率）
```

## 当前状态

### CPU 侧（已完成 ✅）

| 模块 | 状态 | 关键指标 |
| --- | --- | --- |
| 仓库脚手架 | ✅ | MIT，CI 9 job，Python 3.8 语法兼容 |
| 知识库 | ✅ | PRTS 5516 页面 / RAG 13511 chunks / 图谱 3768 节点 / MCP 6 工具 |
| 视觉解析 | ✅ | CV+VLM 双通道骨架，mock 全链路，两帧 OCR 容错 |
| 动作执行 | ✅ | ADB 封装+动作空间+执行器，Mock 记录所有操作 |
| LLM Agent | ✅ | 慢快双脑+桥接预留，决策日志完整可解释，MCPKnowledge 并行<10ms |
| 环境封装 | ✅ | Gym 风格+Mock 环境+奖励评估+对局日志 |
| API 服务 | ✅ | 17 路由+WebSocket，FastAPI，9 接口联调零字段缺失 |
| 训练数据 | ✅ | SFT 18080 条（train 16262/eval 1818），预 tokenize 417 万 token |
| 视频提取 | ✅ | 下载/抽帧/转写/读图/对齐/结构化全链路，chart_reader 完整实现 |
| 前端 | ✅ | Dashboard 骨架（6 模块）+ 知识库前端（3 页）+ 45 前端测试 |
| 测试 | ✅ | 496 测试函数（Python）+ 45（前端），API 集成测试 14 用例 |
| 工程化 | ✅ | 文档一致性/configs 审计/TODO 清单/CI 9 job/项目状态脚本 |

### V100 侧（待办 ⏳）

1. **编译 PointNet2**（毕设仓，最易卡的 CUDA 算子）
2. **加载 Qwen3-8B-Thinking** → 跑 slow.think() 验证输出格式
3. **加载 MiniCPM3-4B** → 快反应真实推理
4. **YOLOv8n 训练**（干员/敌人检测，PRTS 敌人图片+真机截图标注）
5. **SFT 训练**（QLoRA 4bit+LoRA r=16，V100 16GB ~9GB 显存，~2 小时）
6. **DPO 偏好训练**
7. **VLM 慢通道**（Qwen3-VL-8B 或 UI-TARS-7B）
8. **真机联调**（MuMu 模拟器+ADB，简单关卡闭环）

详细清单见 `docs/v100_checklist.md` 和 `docs/v100_handoff.md`。

## 文档索引

| 文档 | 内容 |
| --- | --- |
| `docs/architecture.md` | 整体架构图+模块说明+模块状态表 |
| `docs/setup.md` | 环境搭建 |
| `docs/v100_checklist.md` | V100 上线清单（Step 1 PointNet2 编译） |
| `docs/v100_handoff.md` | V100 上线前必读（环境/模型/待办/验证清单） |
| `docs/api.md` | API 接口文档（17 路由+参数+返回格式+示例） |
| `docs/ci.md` | CI 配置说明（9 个 job） |
| `docs/dashboard_design.md` | Dashboard 设计稿（布局/模块/路由/数据依赖） |
| `docs/frontend_merge_plan.md` | 前端合并方案（frontend/+web/+web-kb/） |
| `docs/project_plan.md` | 项目路线图+里程碑 |
| `docs/troubleshooting.md` | 常见问题（PointNet2/CUDA/OOM/RAG 检索质量） |
| `docs/todo_inventory.md` | TODO 清单与分类（90 V100+5 真机+3 可立即做） |
| `docs/configs_audit.md` | Configs 一致性审计 |
| `docs/docs_consistency_report.md` | 文档一致性审计报告 |
| `docs/sft_data_quality.md` | SFT 数据质量报告 |
| `docs/maa_decision_patterns.md` | MAA 作业决策模式统计（干员出场/费用/技能/位置） |
| `docs/benchmark_baseline.md` | 性能基准基线（RAG/MCP/Agent/视觉） |
| `docs/coverage_report.md` | 测试覆盖率报告 |
| `docs/pipeline_robustness.md` | 数据管线健壮性报告 |
| `docs/logging_guide.md` | 日志规范 |
| `docs/input_validation.md` | 输入验证加固 |
| `docs/error_message_audit.md` | 错误消息质量审计 |
| `docs/type_hints_status.md` | Type Hints 覆盖率状态 |
| `docs/glossary.md` | 术语表（evidence 分级等） |
| `docs/dependencies_audit.md` | 依赖审计 |
| `docs/perf_regression_guide.md` | 性能回归指南 |
| `docs/api_versioning.md` | API 版本化策略 |
| `docs/project_health_report.md` | 项目健康检查总报告 |
| `docs/experiment_log.md` | 实验记录 |
| `docs/pending_decisions.md` | 待用户决策项 |

## 数据与版权

- `data/prts_raw/`、`data/vector_store/`、`data/graph/`、`data/sft_data/`、`data/video_*/`、`weights/`、`results/` 均在 `.gitignore`，**不进入公开仓库**。
- 爬虫脚本可提交，但爬取的 PRTS 数据、游戏截图、游戏素材一律不入库（版权风险）。
- MAA 资源不 vendoring 进库，坐标自行测量或参考后重写，模板图片让使用者自行从 MAA 获取。
- 视频素材（血狼破军等 UP 主）只存本地，绝不提交。

## 贡献指南

1. Fork 并创建分支
2. 确保 `bash scripts/run_smoke.sh` 通过
3. 确保 `python -m pytest tests -q` 通过（新增代码需补测试）
4. 提交信息使用 `.gitmessage` 定义的前缀（feat/fix/docs/refactor/exp/test）
5. GPU 相关代码标注 `# TODO-V100: <具体说明>`
6. 提交 PR

## 致谢

- [PRTS Wiki](https://prts.wiki/) — 干员/敌人/关卡数据来源
- [MAA (MaaAssistantArknights)](https://github.com/MaaAssistantArknights/MaaAssistantArknights) — ADB 控制层与坐标思路参考
- [血狼破军](https://space.bilibili.com/267766441) — 视频分析素材来源（强度榜/DPS 对比）
- [Qwen](https://qwen.ai/) — Qwen3-8B / Qwen3-VL 模型
- [OpenBMB](https://github.com/OpenBMB) — MiniCPM3-4B 模型

## License

MIT License，见 [LICENSE](./LICENSE)。
