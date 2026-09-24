# V100 上线检查清单（v100_checklist）

> 目标机：单卡 V100（sm_70，16G）。所有步骤需在 GPU 机上执行，或按文中标注在任意机器预演。
> 每一步的执行脚本见 `scripts/v100_step*.sh`；本文是人工核对清单，脚本是自动化入口。

## Step 1：环境检查（`scripts/v100_step1_setup.sh`）

- [ ] torch/CUDA：`torch.cuda.is_available()`，`torch.version.cuda` 与 nvcc 一致
- [ ] 算力：`torch.cuda.get_device_capability(0) == (7, 0)`（sm_70）
- [ ] 依赖：peft、trl、transformers、fastapi、chromadb、sentence-transformers、networkx、
  ultralytics、paddleocr、opencv-python、requests、bs4（`pip list | grep`）
- [ ] adb：`adb devices` 能看到 MuMu 模拟器（7555）
- [ ] **不编译 PointNet2**（毕设 pointcloud 仓的 CUDA 算子，与本项目无关）；
  毕设单独隔离环境，见 `docs/troubleshooting.md` 的 V100 小节
- [ ] 项目干净克隆：`git clone` 后 `pip install -r requirements.txt`，`scripts/check_env.sh` 通过

## Step 2：视觉（`scripts/v100_step2_train_vision.sh`）

- [ ] 录制真实出怪时间轴（**第一阶段优先级最高**）：逐关录屏/视觉确认打点，回填
  `configs/perception.yaml` 的 `spawn.timeline`（把 `estimated` 升级为 `annotated`）
- [ ] YOLOv8n 数据准备：截图裁剪/标注（敌人、干员、装置），转 YOLO 格式
- [ ] YOLOv8n 训练/导出：`yolo detect train` → `yolov8n_arknights.pt`，更新
  `perception/detector_yolo.py` 的 `weights` 路径，填充 `detect()` 与 `confirm_spawn()`
- [ ] 校准 ROI：cost_box、技能按钮、卡牌槽、格子网格、enemy_confirm_region（configs/perception.yaml）
- [ ] OCR：`paddleocr` 实测费用/技能冷却，确认 `ocr_cost.py` 的 ROI 与两帧容错有效
- [ ] 冒烟：真实截屏 → `state_parser` 输出 GameState JSON（不依赖 VLM）

## Step 3：SFT（`scripts/v100_step3_sft.sh`，先 CPU 预演再 GPU）

- [ ] CPU 预演：`python -m training.sft_data_prep --job data/sft_data/maa_jobs --prts data/prts_raw --split-by-stage`
  （全量 18080 条，train 16262/eval 1818，切分无同关泄漏，见 `docs/sft_data_quality.md`）
- [ ] 质量审计：`python -m training.sft_quality_audit --file data/sft_data/sft_train.jsonl --n 50`
- [ ] `python -m training.sft_train --dry-run` 在 CPU 验证数据/掩码/训练/存盘代码路径
- [ ] 真机：`python -m training.sft_train`（fp16 显存不足则 `--load-in-8bit` QLoRA，见下）

### Step 4 展开：SFT 精确执行手册（V100 16G）

```bash
# 1) 数据（在任意机器/CPU 完成，产物入 data/sft_data，gitignore）
python -m training.sft_data_prep --job data/sft_data/maa_jobs --prts data/prts_raw --split-by-stage
python -m training.sft_quality_audit --file data/sft_data/sft_train.jsonl --n 50

# 2) CPU 预演（沙箱也做过）：极小随机模型跑真实 LoRA 全链路
python -m training.sft_train --dry-run

# 3) 真机训练（V100，fp16 权重放不下时必须 QLoRA 8bit）
#    fp16 Qwen3-8B 仅权重 ≈16.4GiB > 16G，故默认 QLoRA：
python -m training.sft_train --load-in-8bit
#    显存仍不足时：gradient_checkpointing + micro batch 1；或退回 Qwen3-4B fp16
#    首次请单卡先 `--sample-n 2000` 跑 1 个 epoch 验证管线，再全量
# 4) 产物（gitignore，不入库）
#    weights/sft_qwen3_lora/（adapter 权重）→ 真机评估（Step5）
#    data/sft_data/sft_train.jsonl + sft_eval.jsonl + sft_split_manifest.json
# 5) 记录：docs/experiment_log.md 追加一节（模板见文件头）
```

关键点：**V100 是 sm_70，没有 bf16**，`configs/training.yaml` 里 SFT/DPO 均 `fp16: true / bf16: false`；
`--dry-run` 与真机共用同一份 Qwen3ForCausalLM + peft 调用路径。

## Step 4：部署（`scripts/v100_step4_deploy_agent.sh`）

- [ ] 服务：uvicorn api.server:app（FastAPI，见 docs/api.md）；MCP 服务可选
- [ ] adb：MuMu 7555 连通，`action/adb_controller.py` 实测 tap/swipe
- [ ] 模型：慢思考（Qwen3-8B-Thinking）、快反应（MiniCPM）、VLM（Qwen3-VL/UI-TARS）、
  bridge（latent_bridge）加载完成（`agent/*` 的 TODO-V100 填充点）
- [ ] 组件注入：`env/arknights_env.py` 换真实 perception（ADB+CV）与 executor（ADB）
- [ ] 先打简单关：1-7 / 2-8 / 3-8（决策日志 + 奖励模块评估）

## Step 5：评估（`scripts/v100_step5_eval.sh`，任意机器可先跑 mock 基线）

- [ ] mock 基线：`python -m env.mock_env` 两局（win +100 / lose -30），奖励口径见 env/reward.py
- [ ] 真机批量：`env/arknights_env.py` 循环对局，逐局 `EpisodeLog` 落 `results/episodes/`，
  `api/episode/*` 查询
- [ ] 通关识别：真机结算画面 `is_cleared()` 视觉判定（当前 mock 脚本化）
- [ ] 结果记录：docs/experiment_log.md（胜率/步数/总分/延迟/检索命中）

---

## 附录：假想算力估算（勿当规划依据）

| 场景 | 参数/数据 | 估算 |
|---|---|---|
| YOLOv8n 训练（Step2） | 640px，~2k 图 | <1h（V100） |
| SFT 全量（Step3） | Qwen3-8B LoRA 16G，16262 条 | 约 6-8h（fp16） |
| DPO（后续） | 偏好对 500+，LoRA 16G | 约 2-3h |
| 推理单步 | Qwen3-8B（4bit） | 约 1-2s（CPU 遥不可及，V100 显著快） |

> 以上为粗糙量级，V100 实测后回填真实值；不构成任何性能承诺。
