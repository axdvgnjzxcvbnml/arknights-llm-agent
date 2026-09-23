# V100 上线清单（v100_checklist）

目标机器：单卡 **NVIDIA V100（compute capability sm_70，无 bf16，训练用 fp16）**。
本清单按"先排掉最易卡点 → 再接 arknights 训练/部署"排序。每项给可勾选的检查点。

> 环境隔离建议：毕设栈（Python3.8 / PyTorch1.13.1+CUDA11.7）与 arknights LLM 栈
> 用**不同 conda env**，互不污染。

---

## Step 1 —— 编译 PointNet2 CUDA 算子（毕设，最高优先级，最先做）

这是整条上线链路**最容易卡住**的地方，务必在做任何训练之前先编译并跑通最小算子样例；
不要等模型代码写完再来排 CUDA。

- [ ] 建立/激活**毕设独立 env**：Python3.8 + PyTorch1.13.1+cu117
- [ ] `nvcc --version` 与 `torch.version.cuda` 都是 **11.7**，`CUDA_HOME` 指向 cuda-11.7
- [ ] `export TORCH_CUDA_ARCH_LIST="7.0"`（V100=sm_70）
- [ ] 编译安装 `pointnet2_ops`，最小样例 `furthesh_point_sample(...).cuda()` 跑通
- [ ] **如果编译失败，看 `docs/troubleshooting.md` 的「PointNet2 CUDA 算子编译失败」章节**
      （arch=7.0 / nvcc 与 torch CUDA 对齐 / gcc 版本 / 旧 fork 的 THC·AT_CHECK API）
- [ ] 算子通过后，再继续毕设 VoteNet / YOLOv8n 相关训练；与 arknights env 保持隔离

---

## Step 2 —— arknights 基础环境（对应 scripts/v100_step1_setup.sh，第八批提供脚本）

- [ ] 新建独立 env（建议 Python3.10），`git clone` 本仓库
- [ ] 安装 requirements（GPU 版 torch、transformers、peft、trl、chromadb、
      sentence-transformers、ultralytics、paddleocr 等）
- [ ] `python -c "import torch;print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"`
      输出 True / V100
- [ ] `bash scripts/check_env.sh` 通过；`bash scripts/run_smoke.sh` 三段 mock 全绿（CPU 部分）
- [ ] ADB：`adb connect 127.0.0.1:7555` 能连上 MuMu；真机截屏/点击自测（坐标仍是占位，需校准）

## Step 3 —— 视觉模型训练（对应 v100_step2_train_vision.sh）

- [ ] 按 `perception/detector_yolo.py` 顶部 `# TODO-V100` 准备 YOLOv8n 数据
      （PRTS 敌人图片 + 真机截图标注；**数据不入库**）
- [ ] 训练干员/敌人检测，替换 mock；`confirm_spawn` 真实接 YOLO 输出，把波次 estimated→cv
- [ ] PaddleOCR 费用识别真机校准（`configs/perception.yaml` 的 cost_box）
- [ ] 校准占位坐标：grid / operator_card_bar / skill_buttons / enemy_confirm_region
- [ ] 录制**真实波次时间轴**替换均匀估算（architecture 既定第一步）

## Step 4 —— 知识库与 SFT/DPO（对应 v100_step3_sft.sh）

- [ ] 在可联网环境跑爬虫 + `build_rag.sh` + `build_graph.sh`（产物落 data/，gitignore）
- [ ] embedding 切到 `device: cuda`（`configs/knowledge.yaml`），重建 ChromaDB
- [ ] 准备自己的对局/作业 → `python -m training.sft_data_prep` 生成 SFT JSONL
- [ ] 补齐 `training/sft_train.py` 的 `# TODO-V100`（**fp16 非 bf16**），LoRA 训练出权重
- [ ] （可选）整理偏好对后跑 `training/dpo_train.py`

## Step 5 —— 部署 Agent（对应 v100_step4_deploy_agent.sh）

- [ ] 慢思考 Qwen3-8B-Thinking、快反应小模型、VLM（Qwen3-VL-8B / UI-TARS-7B）加载到 V100
- [ ] 接 `agent/slow_thinker.py / fast_reactor.py / latent_bridge.py` 的 `# TODO-V100`
- [ ] MCP server（knowledge/mcp_tools/server.py）作为工具被 Agent 调用联通
- [ ] 用真实 perception + executor 注入 `env/ArknightsEnv`，先打简单关

## Step 6 —— 评估（对应 v100_step5_eval.sh）

- [ ] 用 `env/reward.py` 的评估口径（通关/漏怪/费用溢出）批量跑分，出对局报告
- [ ] 记录到 `docs/experiment_log.md`，对比 mock→真机、慢思考开/关、RAG 开/关
- [ ] 核对每次决策的 reasoning / evidence 分级是否合理（retrieved/inferred 不得当事实）

---

## 上线红线（每步都检查）

- [ ] PRTS 爬取数据、游戏截图/素材、MAA 模板、权重、results **不进公开仓库**（.gitignore）
- [ ] MAA 仅作接口/坐标参考后自测重写，不分发其代码与资源；README 保留署名
- [ ] 所有 GPU 路径在真机跑通前都应保留可回退的 mock，保证 CPU 冒烟始终绿
