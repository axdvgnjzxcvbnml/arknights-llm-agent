# scripts（一键脚本）

所有脚本以项目根为工作目录（`cd "$(dirname "$0")/.."`），带前置检查，
成功后打印"下一步"提示。`# TODO-V100` 标注的步骤只在 V100 真机执行。

| 脚本 | 作用 |
|---|---|
| `setup_env.sh` | 安装/校验 Python 依赖（`--minimal` 只查版本；`ARK_SKIP_PIP=1` 跳过 pip） |
| `crawl_prts.sh` | 爬取 PRTS 语料 `[operator|enemy|stage|all] [limit]`（限速/退避/断点） |
| `build_rag.sh` | 构建 RAG 向量库（ChromaDB + bge）；`ARK_REBUILD=1` 全量重建 |
| `build_graph.sh` | 构建知识图谱（NetworkX → GraphML，供 api/图谱接口只读） |
| `v100_step1_setup.sh` | V100 环境检查（torch/CUDA/sm_70/依赖/adb），不编译 PointNet2 |
| `v100_step2_train_vision.sh` | V100 视觉训练清单（YOLO/时间轴校准） `# TODO-V100` |
| `v100_step3_sft.sh` | V100 SFT（先 CPU 跑数据准备，再 GPU 训练） `# TODO-V100` |
| `v100_step4_deploy_agent.sh` | V100 部署（adb/模型/注入，先 mock 回归） `# TODO-V100` |
| `v100_step5_eval.sh` | 评估（任意机器先跑 mock 基线；真机批量 `# TODO-V100`） |

GPU 门禁：`v100_step2/3/4` 开头检查 `torch.cuda.is_available()`，无 CUDA 时以
退出码 3 安全中止（不做假训练）；`step1` 只检查（无 GPU 仅告警）；`step5` 任意机器可跑 mock。
