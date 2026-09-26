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
- [ ] 准备自己的对局/作业 → `python -m training.sft_data_prep --split-by-stage`
      生成按关卡分组、无泄漏的 sft_train/eval.jsonl
- [ ] 先在 CPU 自检管线：`python -m training.sft_train --dry-run --max-steps 2`
- [ ] V100 上按下方《SFT 精确执行手册》跑 LoRA/QLoRA（**fp16 非 bf16**）出 adapter
- [ ] （可选）整理偏好对后跑 `training/dpo_train.py`

### Step 4 展开：SFT 精确执行手册（Qwen3-8B + LoRA / V100 16G）

**0. 数据现状（第十批已在 CPU 侧备好，data/ 不入库）**

- 真实 MAA 作业 K=1：原始 20180 动作 → 剔除泛称/灵活位占位 1646、无名动作 1、
  精确去重 453，**入训 18080 条**；
  按**关卡维度**分组切分：train 16262（2713 关）/ eval 1818（300 关），关卡交集 0（防泄漏）。
- 文件名与 `configs/training.yaml` 对齐：`data/sft_data/sft_train.jsonl` / `sft_eval.jsonl`；
  切分清单 `data/sft_data/sft_split_manifest.json`（由数据准备脚本自动生成），
  数据质量结论见 `docs/sft_data_quality.md`。
- question/answer 实测字符长 max 578/592（token 远小于 2048），训练不会因超长切掉 answer。

**1. 环境（arknights 独立 env，Python 3.10，勿与毕设 env 混用）**

```bash
pip install "torch>=2.1,<2.5" --index-url https://download.pytorch.org/whl/cu118
pip install "transformers>=4.51" peft accelerate "bitsandbytes>=0.43" safetensors sentencepiece
```

- Qwen3 建模需要 `transformers>=4.51`；装机后先确认：
  `python -c "from transformers import AutoModelForCausalLM;import torch;print(torch.cuda.is_available())"`。
- V100 sm_70 **无 bf16**：用 fp16（`configs/training.yaml` 已 `fp16:true / bf16:false`）。
- 首次会联网拉 Qwen3-8B 权重（约 16GB 磁盘）；离线机先 `huggingface-cli download Qwen/Qwen3-8B` 再离线。

**2. LoRA 配置（即 configs/training.yaml `lora`，无需改）**

| 项 | 值 |
|---|---|
| r / lora_alpha | 16 / 32（alpha=2r） |
| lora_dropout | 0.05 |
| bias | none |
| target_modules | q,k,v,o,gate,up,down 七个投影 |
| task_type | CAUSAL_LM |

LoRA 参数量约 44M（约占 Qwen3-8B 8.2B 参数的 0.5%；GQA 下 k/v 投影更小）；
只存 adapter（fp16 约 90–120MB/个），不存全量 8B。

**3. 训练超参（即 configs/training.yaml `sft`）**

| 项 | 值 | 说明 |
|---|---|---|
| num_train_epochs | 3 | eval 上观察过拟合再减 |
| per_device_train_batch_size | 1 | 16G 必须 1 |
| gradient_accumulation_steps | 16 | 有效批 = 16 |
| learning_rate | 2e-4 | LoRA 常用区间 |
| lr_scheduler / warmup_ratio | cosine / 0.03 | |
| max_length | 2048 | 实测样本 token 远小于此；显存紧可降到 1024 |
| fp16 / gradient_checkpointing | true / true | V100 必开梯度检查点 |
| optim | adamw_torch | |

**4. 显存预估（V100 16GB = 约 15.6 GiB 可用）——务必先看**

- **纯 fp16 全量 Qwen3-8B（约 8.2B 参数）权重 ≈ 16.4 GiB，仅权重就已超过 16GB 卡可用容量**，
  再加 LoRA 优化器状态与激活必 OOM。
  因此 16G **默认走 QLoRA**（脚本 `SFT_LOAD_8BIT` 默认 1）：
  - 8bit 冻结底座 ≈ 8.0–8.5 GiB（8.2GB 权重 + 量化 scale/开销）；LoRA 参数+梯度+AdamW(fp32 m/v) ≈ 0.5–0.7 GiB；
    梯度检查点后激活：bs1 × 1024 ≈ 1–1.5 GiB、× 2048 ≈ 2–3 GiB。
  - 合计 **seq1024 ≈ 10–11 GiB；seq2048 ≈ 11.5–13.5 GiB**，16G 可跑但偏紧，建议先 seq1024。
- 不想用 8bit：只能换更小底座（Qwen3-4B fp16 ≈ 8GB 权重）再配 LoRA。
- 8bit 在 sm_70 可用（bitsandbytes 8bit Linear/优化器支持 V100）；若版本不兼容，回退 Qwen3-4B fp16。

**5. 训练时间估算（先测再信）**

- 优化器步数 = train 16262 ÷ 有效批16 ≈ **1017 步/epoch × 3 ≈ 3050 步**（micro 步约 48786）。
- 平均序列按约 350–450 token 估，总 token 约 2×10^7；V100 + QLoRA + 梯度检查点的实际
  吞吐通常 1500–3000 token/s，粗估 **3–6 小时**（差异大，勿当定值）。
- 正式开训前脚本自动跑 **5 步探针**：读 `logging_steps=10` 的 loss 与 `nvidia-smi` 峰值显存、
  单步耗时，用 `总micro步 × 单步耗时` 现场校准总时长。

**6. checkpoint 策略（configs/training.yaml 已配）**

- `save_steps=200`、`save_total_limit=2`：约每 200 优化器步存一次，只保留最近 2 个，省盘。
- 只存 LoRA adapter + tokenizer 到 `weights/sft_qwen3_lora/`（gitignore）；
  恢复训练用 `Trainer`/循环的 resume 机制按最新 checkpoint 续跑。
- 训练结束务必另存一份“eval loss 最低”的 adapter（手动从最近 checkpoints 中保留），防止末轮过拟合。

**7. 数据/显存超限的应对（按命中类型选）**

- 显存（激活）爆：确认 `gradient_checkpointing=true`；`max_length` 2048→1024（本数据 p99 足够）；
  微批恒为 1，用 accum 补有效批；启动加
  `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`；关掉占显存的其它进程。
- 显存（权重）爆：用 `--load-in-8bit`（默认）或换 Qwen3-4B；不要在 16G 上硬上 fp16 8B。
- 系统内存/数据量：18k 条 JSONL 仅数 MB，可全量进内存；将来扩到很大时改为**分片 JSONL +
  流式 IterableDataset 按需读盘**（不要一次性 load），并按长度近似排序减少 padding 浪费。
- 磁盘：8B 权重约 16GB + adapter（各约 150MB ×2）；预留 ≥ 40GB。

**8. 开训命令与验收**

```bash
bash scripts/v100_step3_sft.sh           # 默认 QLoRA；内含 CPU 数据准备 + GPU 门禁 + 5 步探针
# 或手动：python -m training.sft_train --load-in-8bit
```

- 探针 loss 应有限且整体下行；正式训练 loss 曲线正常、无 NaN（fp16 若出 NaN 可加 clip）。
- 训完在 eval 1818 条（覆盖 **300 个 train 中未出现的关卡**）上算 loss / 动作正确率，记入
  `docs/experiment_log.md`；评估只对 answer 计 loss（prompt mask 已在编码层保证）。


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

## Step 7 —— 离线视频信息提取 → 视频 SFT（第十四批，`video_extract/`，非实时链路）

这是离线数据生产线，可与 Step 3/4 并行，不影响在线 Agent。

- [ ] 在能联网、已装 `yt-dlp` 与系统 `ffmpeg` 的机器上，于 `video_extract/config.yaml`
      填血狼破军真实 B 站 `uid`（仓库留空，不臆造）；确认 B 站 robots/使用条款允许
- [ ] 先小批量：`YtDlpDownloader.list_uploader_videos(uid, limit=5)` → `batch_download(...)`
      （限速/间隔/退避/断点续爬已内置）；素材落 `data/video_raw/`（gitignore，不提交）
- [ ] V100 上配置并安装 ASR：`asr.backend=whisper`、`asr.model=Systran/faster-whisper-large-v3`、
      `device=cuda`、`compute_type=float16`；`pip install faster-whisper`，跑 `transcriber`
- [ ] V100 上配置 VLM：`vlm.backend=qwen3vl`、`vlm.model=Qwen3-VL-8B 或 UI-TARS-7B`、
      `device=cuda`；实现 `chart_reader.read_chart` 的表格/榜单→JSON（`# TODO-V100`）
- [ ] 抽帧：先用 `frames.mode=interval`（5s）跑通，再评估 `scene` 场景切换模式降冗余
- [ ] `aligner`（CPU）+ `structurer`（CPU）无需改动，直接产 `data/sft_data/video_sft.jsonl`
- [ ] 抽查：口播↔图表对齐是否合理（必要时调 `align.tolerance_sec` 或上 VAD/字幕精校）；
      证据保持 chart/speech=retrieved、alignment=inferred，每条带 BV + 时间戳
- [ ] 视频 SFT 与 MAA/PRTS SFT 合并训练前，按既有"按关卡/来源维度切分"原则避免泄漏

---

## 上线红线（每步都检查）

- [ ] PRTS 爬取数据、游戏截图/素材、MAA 模板、**视频/音频/抽帧（data/video_raw、data/video_frames）**、权重、results **不进公开仓库**（.gitignore）
- [ ] 视频为第三方版权素材：只本地训练用，不分发媒体文件；SFT 中保留 UP 主来源与"第三方分析"标注
- [ ] MAA 仅作接口/坐标参考后自测重写，不分发其代码与资源；README 保留署名
- [ ] 所有 GPU 路径在真机跑通前都应保留可回退的 mock，保证 CPU 冒烟始终绿
