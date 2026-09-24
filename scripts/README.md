# scripts —— 工具脚本

| 脚本 | 用途 | 状态 |
|---|---|---|
| `run_smoke.sh` | 冒烟测试（mock 全链路，CPU 可跑，无 GPU/模拟器/数据），三段 | ✅ 视觉 + Agent + 环境 |
| `smoke_perception.py` | 截屏→OCR/地图→状态(波次+敌情确认)→VLM→状态报告→`[7/7]` MockActionExecutor 动作编排 | ✅ |
| `smoke_agent.py` | Agent 闭环：感知→知识→慢思考→桥接→快反应→执行→反思，落可解释决策日志 | ✅ 第五批 |
| `smoke_env.py` | Gym 风格环境跑完整两局：10 步通关 / 3 步失败，落对局报告（含每步奖励） | ✅ 第六批 |
| `check_env.sh` | 环境检查（必需依赖缺失则失败；GPU/adb 仅提示） | ✅ |
| `setup_env.sh` | 安装依赖 + 关键库版本检查（`--minimal` 最小依赖；`ARK_SKIP_PIP=1` 仅查版本） | ✅ 第八批 |
| `crawl_prts.sh` | 一键批量爬 PRTS：`bash crawl_prts.sh [operator\|enemy\|stage\|all] [limit]`，默认 50/50/20，限速/退避/断点续爬 | ✅ 第八批（联网，产物 gitignore） |
| `build_rag.sh` | 从 `data/prts_raw` 构建 ChromaDB 向量库（默认 upsert；`ARK_REBUILD=1` 重建） | ✅ 第八批 |
| `build_graph.sh` | 构建 NetworkX 知识图谱（GraphML + stats） | ✅ 第八批 |
| `v100_step1_setup.sh` | V100 环境检查（GPU/CUDA/sm_70/依赖/adb）；**不编译 PointNet2**（属毕设仓），无 GPU 仅告警，退出 0 | ✅ 第八批 |
| `v100_step2_train_vision.sh` | 视觉训练：无 CUDA 门禁退出 3；有 CUDA 给 `# TODO-V100` 训练清单 | ⏳ 第八批骨架 |
| `v100_step3_sft.sh` | 先 CPU 生成 SFT 数据，再 GPU 门禁；`sft_train` 现按设计抛 TODO-V100 | 🟡 第八批骨架 |
| `v100_step4_deploy_agent.sh` | 知识库检查→mock 回归→GPU 门禁（无 CUDA 退出 3）；真机/模型接入清单 | 🟡 第八批骨架 |
| `v100_step5_eval.sh` | 任意机器跑 mock 评估基线（reward/对局报告）；真机批量评估 TODO-V100 | 🟡 第八批骨架 |

> GPU 门禁约定：`step2/step3/step4` 在无 CUDA 机器以**退出码 3** 安全中止（不做假训练）；
> `step1` 只检查（退出 0）；`step5` 始终先跑 mock 评估。每个脚本结尾都打印"下一步"。

## 知识库流水线（CPU 可复现）

```bash
bash scripts/setup_env.sh            # 装依赖（或 --minimal）
bash scripts/crawl_prts.sh all       # 联网爬取 -> data/prts_raw（gitignore）
bash scripts/build_rag.sh            # -> data/vector_store（gitignore）
bash scripts/build_graph.sh          # -> data/graph（gitignore）
python -m knowledge.rag.retrieval_test   # 检索相关性验证
python -m knowledge.graph.query_graph     # 图谱查询验证
```

## V100 上线流水线

```bash
bash scripts/v100_step1_setup.sh            # 环境检查（不编译 PointNet2）
bash scripts/v100_step2_train_vision.sh     # 视觉训练（需 CUDA）
bash scripts/v100_step3_sft.sh              # SFT 数据准备 + LoRA 微调（需 CUDA）
bash scripts/v100_step4_deploy_agent.sh     # 知识库就绪 + mock 回归 + 真机部署
bash scripts/v100_step5_eval.sh             # mock 基线 + 真机端到端评估
```


## run_smoke.sh

```bash
bash scripts/run_smoke.sh
```

第三批覆盖视觉 mock 全链路，末尾打印「游戏状态报告」（费用/手牌/技能/波次(含
estimated·cv 标注)/可部署格/VLM 局势与建议/证据分级），并落一份到
`results/perception_smoke_report.txt`（results 已 gitignore），含完整性断言。

第五批新增第二段 `smoke_agent.py`：跑一个会随部署演进的假战局（先锋→医疗→狙击→等待），
逐步打印慢思考 reasoning、evidence 引用、慢快桥接、快通道拦截、执行结果与自我反思，
完整可解释决策日志落到 `results/agent_decision_log.txt`（gitignore），含 14 项完整性断言。
两段任一断言不满足则非 0 退出。
