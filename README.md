# arknights-llm-agent

> 能看、能想、能打、能解释的明日方舟 AI Agent —— 基于 LLM Agent + RAG + MCP，不使用 RL。

## 项目简介

本项目构建一个"看-想-打-解释"全闭环的明日方舟 AI Agent：

- **能看**：ADB 截屏 + YOLOv8 目标检测（干员/敌人）+ PaddleOCR（费用识别），把游戏画面解析成结构化状态；
- **能想**：慢思考模型（Qwen3-8B-Thinking）结合 RAG 检索结果与知识图谱，给出带依据的决策；快反应模型（MiniCPM 级小模型）负责低延迟即时操作；
- **能打**：动作执行器把决策转成 ADB 命令，驱动 MuMu 模拟器部署干员、释放技能、撤退；
- **能解释**：每次决策输出 `reasoning` 字段，包含决策依据与知识引用，便于调试、复盘与展示。

技术路线为 **LLM Agent + RAG + MCP 工具**，**不使用强化学习（RL）**。目标先在简单关卡上跑通 mock 全链路闭环，再逐步扩展到真实关卡与肉鸽（Roguelike）模式。

## 核心技术栈

| 模块 | 方案 |
|---|---|
| 慢思考 LLM | Qwen3-8B-Thinking（V100 部署） |
| 快反应 LLM | MiniCPM 等小模型（TODO-V100） |
| 知识库 | ChromaDB + BAAI/bge-small-zh-v1.5 + NetworkX 知识图谱 |
| 工具协议 | MCP（参考 PRTS MCP Server 的工具集） |
| 视觉感知 | YOLOv8（干员/敌人检测）+ PaddleOCR（费用识别） |
| 动作执行 | ADB + MuMu 模拟器（adb connect 127.0.0.1:7555） |
| 进程通信 | gRPC / Redis（mock 阶段可直连函数调用） |

## 技术路线图

- [ ] **P0 脚手架与 mock 全链路（CPU 可跑）**：仓库初始化、模块骨架，跑通"截屏→解析→检索→决策→执行"的 mock 端到端流程。
- [ ] **P1 知识库**：PRTS Wiki 爬虫、RAG 向量检索、知识图谱、MCP 工具集。
- [ ] **P2 真实视觉**：YOLO 检测与 OCR 在 V100 上训练/推理，地图解析。
- [ ] **P3 决策闭环**：慢思考 + 快反应 + 桥接，决策循环带完整日志。
- [ ] **P4 V100 训练**：SFT + DPO 微调、视觉模型训练、上线部署。
- [ ] **P5 扩展**：肉鸽模式、集成测试、效果评估。

## 目录结构

```
arknights-llm-agent/
├── agent/                  # LLM Agent 核心（慢思考/快反应/桥接/决策循环）
│   └── prompt_templates/   # Prompt 模板（system/decision/reasoning/self_reflect）
├── knowledge/              # 知识库
│   ├── crawler/            # PRTS Wiki 爬虫（干员/敌人/关卡/攻略）
│   ├── rag/                # 检索增强（Embedding + ChromaDB + Retriever）
│   ├── graph/              # 知识图谱（NetworkX）
│   └── mcp_tools/          # MCP 工具定义
├── perception/             # 视觉解析（ADB 截屏/YOLO/OCR/地图/状态转文本）
├── action/                 # 动作执行（ADB 控制/动作空间/执行器）
├── env/                    # 环境封装（Gym 风格/mock/奖励评估）
├── training/               # V100 训练（SFT/DPO）
├── configs/                # 配置文件（路径/模型名/超参不硬编码）
├── scripts/                # 工具脚本（含 V100 上线五步）
├── data/                   # 数据（mock 可提交，其余 gitignore）
│   ├── prts_raw/           # 原始爬取数据（不提交，版权风险）
│   ├── vector_store/       # 向量库（不提交）
│   ├── graph/              # 知识图谱（不提交）
│   ├── sft_data/           # SFT 训练数据（不提交）
│   └── mock/               # Mock 数据（提交，冒烟测试用）
├── weights/                # 模型权重（不提交）
├── results/                # 结果输出（不提交）
├── tests/                  # 单元测试
├── docs/                   # 文档
└── .github/workflows/      # CI（语法检查 + 冒烟测试 + 环境检查）
```

## 快速开始

### 环境要求

- Python >= 3.8（代码强制通过 3.8 语法检查；开发建议 3.10+）
- 冒烟测试**不需要** GPU、模拟器、PRTS 数据

### 安装与冒烟测试

```bash
git clone <仓库地址> arknights-llm-agent
cd arknights-llm-agent
python -m venv .venv && source .venv/bin/activate
pip install -e .
bash scripts/run_smoke.sh    # mock 全链路：截屏→解析→检索→决策→执行
```

`scripts/run_smoke.sh` 用 mock 视觉与 mock LLM 验证模块间接口，不依赖真实环境。

### 数据与版权声明

`data/prts_raw/`、`data/vector_store/`、`data/graph/`、`data/sft_data/`、`weights/`、`results/` 均已加入 `.gitignore`，**不会**进入公开仓库。爬虫脚本可以提交，但爬取到的 PRTS 数据、游戏截图与游戏素材一律不入库（版权风险）。

## V100 上线指南（简版）

| 步骤 | 脚本 | 内容 |
|---|---|---|
| 1. 环境准备 | `scripts/v100_step1_setup.sh` | 驱动、CUDA、Python 环境 |
| 2. 视觉训练 | `scripts/v100_step2_train_vision.sh` | YOLOv8 / OCR 数据准备与训练 |
| 3. LLM 微调 | `scripts/v100_step3_sft.sh` | SFT（LoRA）→ DPO |
| 4. 部署 | `scripts/v100_step4_deploy_agent.sh` | Qwen3-8B-Thinking 推理服务 |
| 5. 评估 | `scripts/v100_step5_eval.sh` | 关卡胜率 / 延迟 / 可解释性评估 |

详细清单见 `docs/v100_checklist.md` 与 `docs/setup.md`。

## 文档

- `docs/architecture.md` — 整体架构与模块说明
- `docs/setup.md` — 环境搭建
- `docs/v100_checklist.md` — V100 上线清单
- `docs/troubleshooting.md` — 常见问题
- `docs/experiment_log.md` — 实验记录
- `docs/project_plan.md` — 路线图与里程碑

## License

MIT License，见 [LICENSE](./LICENSE)。
