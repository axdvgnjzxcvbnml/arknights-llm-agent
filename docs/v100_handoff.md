# V100 上线前必读（v100_handoff）

> 本文是散落在 `v100_checklist.md` / `troubleshooting.md` / `architecture.md` /
> `configs/` / 审计报告中的 V100 相关内容的**汇总入口**。上线前按本文顺序走，
> 细节回链到对应文档。

**目标机器**：单卡 NVIDIA V100（compute capability **sm_70**，**无 bf16 张量核**，训练/推理统一用 **fp16**）。
**核心约束**：CPU 沙箱只产出代码骨架与 mock，所有真实模型加载/训练/推理在 V100 上完成；
数据/素材/权重绝不进公开仓库。

---

## 一、上线顺序（按优先级，先排掉最易卡点）

| 优先级 | 步骤 | 对应脚本/文档 | 预计卡点 |
|--------|------|--------------|----------|
| **P0** | 编译 PointNet2 CUDA 算子（毕设仓） | `pointcloud-registration-detection` 仓 + `troubleshooting.md` PointNet2 章节 | **最易卡**，最先做 |
| P1 | arknights 基础环境 + GPU 自检 | `scripts/v100_step1_setup.sh` | torch CUDA 版本对齐 |
| P2 | 加载 Qwen3-8B（慢思考） | `agent/slow_thinker.py` TODO-V100 | 16G 显存偏紧，需 QLoRA/8bit |
| P3 | 加载 Qwen3-VL-8B / UI-TARS-7B（VLM 慢通道） | `perception/vlm_analyzer.py` TODO-V100 | 多模型共存显存 |
| P4 | 视觉模型训练（YOLOv8n + PaddleOCR 校准） | `scripts/v100_step2_train_vision.sh` | 数据标注/坐标校准 |
| P5 | SFT 训练（Qwen3-8B + LoRA/QLoRA） | `scripts/v100_step3_sft.sh` + `v100_checklist.md` Step 4 | 显存/训练时间 |
| P6 | 部署 Agent 端到端（慢+快+VLM+MCP+env） | `scripts/v100_step4_deploy_agent.sh` | 模块联调 |
| P7 | 评估 + 实验记录 | `scripts/v100_step5_eval.sh` | — |
| 并行 | 离线视频信息提取 → 视频 SFT | `video_extract/` + `v100_checklist.md` Step 7 | 与在线链路无关，可并行 |

> **P0 必须最先做**：PointNet2 是毕设的 CUDA 算子，整条链路最容易卡的地方。
> 如果编译失败，看 `docs/troubleshooting.md` 的「PointNet2 CUDA 算子编译失败」章节。

---

## 二、环境配置要点

### 2.1 双 env 隔离（必须）

毕设栈与 arknights LLM 栈用**不同 conda env**，互不污染：

| env | Python | PyTorch | CUDA | 用途 |
|-----|--------|---------|------|------|
| 毕设 env | **3.8** | **1.13.1** | **11.7** | PointNet2 / VoteNet / YOLOv8n |
| arknights env | **3.10** | ≥2.1,<2.5 | 11.8（cu118 wheel） | Qwen3 / transformers / peft |

### 2.2 dtype 必须是 float16（V100 sm_70 无 bf16）

**上线前必须检查并修正以下配置**：

- `configs/agent.yaml`：slow_thinker / fast_reactor 的 `dtype` 已为 `float16` ✓
- `configs/training.yaml`：
  - `sft.fp16: true` / `sft.bf16: false` ✓
  - `dpo.fp16: true` ✓
  - ⚠️ **`model.torch_dtype: bfloat16` 需改为 `float16`**（当前注释已标注，但值未改；
    这是加载底座模型时的 dtype，V100 上 bf16 会回退到软件模拟或报错）

代码中的报错文案也已同步为 float16（`agent/slow_thinker.py` / `fast_reactor.py`）。

### 2.3 PointNet2 编译要点（毕设 env）

```bash
export TORCH_CUDA_ARCH_LIST="7.0"   # V100=sm_70，必须
export CUDA_HOME=/path/to/cuda-11.7
nvcc --version   # 必须 11.7
python -c "import torch; print(torch.version.cuda)"  # 必须 11.7
pip install -e pointnet2_ops   # 在算子包目录内
```

最小验证样例（能跑通即算子/CUDA 链路正常）：
```python
import torch, pointnet2_ops
from pointnet2_ops import pointnet2_utils as u
x = torch.randn(2, 1024, 3).cuda()
idx = u.furthest_point_sample(x, 64)
print(idx.shape, idx.device)
```

常见坑（详见 `troubleshooting.md`）：
- `nvcc` 与 `torch.version.cuda` 不一致 → 对齐到 11.7
- `no kernel image available` → `TORCH_CUDA_ARCH_LIST=7.0` 未生效，清 build 缓存重装
- gcc 版本过高（>10）→ 降 gcc 或用 conda 安装兼容版本
- 旧 fork 的 `THC/AT_CHECK` API 不兼容新版 PyTorch → 用已适配的 fork

### 2.4 OOM 应对（V100 16GB）

- Qwen3-8B fp16 全量权重 ≈ 16.4 GiB，**仅权重就超 16G** → 默认走 **QLoRA（8bit 底座）**
- 8bit 冻结底座 ≈ 8.0–8.5 GiB；LoRA 参数+梯度+AdamW ≈ 0.5–0.7 GiB；梯度检查点后激活
  seq1024 ≈ 1–1.5 GiB、seq2048 ≈ 2–3 GiB → 合计 seq1024 ≈ 10–11 GiB，seq2048 ≈ 11.5–13.5 GiB
- 微批恒为 1，用 `gradient_accumulation_steps=16` 补有效批
- 启动加 `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`
- 多模型共存（Qwen3-8B + Qwen3-VL + MiniCPM3）时需评估显存，可能需要分时加载或换更小底座

---

## 三、模型清单（V100 上需要部署的所有模型）

| 模型 | 用途 | 加载位置 | 预估显存（fp16） | 备注 |
|------|------|----------|-------------------|------|
| **Qwen3-8B** / Qwen3-8B-Thinking | 慢思考（决策+推理+RAG 综合） | `agent/slow_thinker.py` | 全量 16.4G / 8bit 8–8.5G | SFT 基座；推理时可加载 LoRA adapter |
| **openbmb/MiniCPM3-4B** | 快反应（即时操作序列） | `agent/fast_reactor.py` | 全量 ≈ 8G | 注意：`MiniCPM-4B` 不存在，用 `MiniCPM3-4B`（已核实） |
| **Qwen3-VL-8B** 或 **UI-TARS-7B** | VLM 慢通道（局势理解/图表读取/可解释推理） | `perception/vlm_analyzer.py` | 全量 ≈ 16G / 8bit ≈ 8G | 二选一；视频图表读取也用此模型 |
| **YOLOv8n** | 敌人/干员检测（confirm_spawn） | `perception/detector_yolo.py` | ≈ 6–10MB（nano 级） | 需训练（PRTS 敌人图 + 真机截图标注） |
| **PaddleOCR**（PP-OCRv4） | 费用/冷却数字识别 | `perception/ocr_cost.py` | CPU 可跑，GPU 加速 | 真机校准 cost_box 坐标 |
| **BAAI/bge-small-zh-v1.5** | 中文 embedding（RAG） | `knowledge/rag/embedding.py` | ≈ 100MB | CPU 可跑，V100 上切 `device:cuda` 加速建库 |
| **Whisper** / faster-whisper-large-v3 | 视频口播 ASR（离线 SFT） | `video_extract/transcriber.py` | ≈ 3G（large-v3） | **可选**，仅视频 SFT 生产线用 |
| **latent_bridge 投影器** | 慢思考隐藏态 → 快反应输入空间 | `agent/latent_bridge.py` | 待定义（小型 MLP） | **M1 待办**：V100 上文字桥接跑通后再考虑实现 |

> **显存共存策略**：Qwen3-8B（8bit）+ Qwen3-VL（8bit）+ MiniCPM3（fp16）≈ 8+8+8 = 24G，
> 超 16G。实际部署需**分时加载**（慢思考时卸载 VLM，VLM 分析时卸载慢思考），
> 或用更小底座（Qwen3-4B 慢思考 + Qwen3-VL-4B）。这是 V100 部署阶段必须实测的事。

---

## 四、V100 上线后待办清单（从审计报告/待确认项提取）

| 编号 | 待办 | 优先级 | 说明 |
|------|------|--------|------|
| **M1** | latent_bridge 真实投影器实现 | 中 | 当前接口已预留（ThinkResult.hidden_state + project() fallback）；V100 上文字桥接跑通后再决定是否实现隐藏态投影 |
| **M6** | 爬虫解析器单测补充 | 低 | 当前 chunking/规则推导已有单测；PRTS HTML 解析器需小 HTML fixture，工作量大，可后续补 |
| **D1** | `/api/training/runs` + `/api/training/metrics` 接真实数据 | 高 | 当前返回空/409；V100 训练开始后读 `results/metrics.jsonl`，前端训练进度卡片才能显示真实 loss 曲线 |
| **D2** | `live_state.push()` 接入 `ArknightsEnv.run_episode()` | 高 | 当前 push 无生产调用；V100 跑局时每步调用 `app.state.live_state.push(frame)`，前端 `/ws/live` 才能收到真实帧 |
| **D3** | `configs/training.yaml` 的 `model.torch_dtype` 改 float16 | 高 | 当前是 bfloat16（注释已标注但值未改）；V100 加载模型前必须改 |
| **D4** | 视觉模型训练 + 坐标校准 | 高 | YOLOv8n 训练、PaddleOCR cost_box 校准、grid/operator_card/skill_button/enemy_confirm_region 占位坐标校准、真实波次时间轴录制 |
| **D5** | 慢思考/快反应/VLM 的 TODO-V100 真实实现 | 高 | `slow_thinker.py` / `fast_reactor.py` / `vlm_analyzer.py` / `detector_yolo.py` / `transcriber.py` / `chart_reader.py` 的真实模型加载与推理 |
| **D6** | MCP server 与 Agent 联通 | 中 | `knowledge/mcp_tools/server.py` 作为工具被 LLM Agent 调用（当前工具是纯函数，Agent 侧未接 MCP client） |
| **D7** | 前端 node 邻居查询分组配额 + 反向"推荐关卡"接口 | 低 | AUDIT 4.4 待办；等两个 web 合并、Dashboard 做完后统一处理 |
| **D8** | 视频 SFT 与 MAA/PRTS SFT 合并训练 | 中 | `video_extract/` 产 `video_sft.jsonl` 后，按关卡/来源维度切分避免泄漏，与现有 18080 条合并 |

---

## 五、验证清单（每一步的验证方法）

### P0 PointNet2
- [ ] `import pointnet2_ops` 不报错
- [ ] `furthest_point_sample(torch.randn(2,1024,3).cuda(), 64)` 输出 shape=(2,64)、device=cuda
- [ ] 毕设 VoteNet 推理一次，mAP ≈ 57.7（与论文/基线一致）

### P1 基础环境
- [ ] `torch.cuda.is_available()` = True，`torch.cuda.get_device_name(0)` = V100
- [ ] `bash scripts/check_env.sh` 通过
- [ ] `bash scripts/run_smoke.sh` 四段全绿（CPU mock 部分）
- [ ] `adb connect 127.0.0.1:7555` 连上 MuMu，截屏/点击自测

### P2 Qwen3-8B 慢思考
- [ ] `python -c "from transformers import AutoModelForCausalLM; ..."` 加载成功（8bit）
- [ ] `MockSlowThinker` 替换为真实 `SlowThinker`，`think(state, knowledge)` 输出符合
  `AgentDecision` schema（reasoning + action + confidence + knowledge_used）
- [ ] 单次推理延迟 < 10s（V100 + 8bit + LoRA）
- [ ] `tests/test_agent.py` 的 mock 用例仍通过（真实用例 skip）

### P3 VLM
- [ ] Qwen3-VL-8B / UI-TARS-7B 加载成功
- [ ] `VLMAnalyzer.analyze(screenshot, state)` 输出符合 `VLMAnalysis` schema
  （situation + strategic_advice + confidence + evidence）
- [ ] evidence 恒为 inferred（VLM 输出是推断，不是事实）

### P4 视觉
- [ ] YOLOv8n 训练完成，mAP 达标（干员/敌人检测）
- [ ] `confirm_spawn(enemy_name, frame)` 能把 SpawnTracker 状态从 estimated 升级为 cv
- [ ] PaddleOCR 费用识别准确率 > 95%（真机校准后）
- [ ] 地图格子解析与 PRTS 关卡布局一致

### P5 SFT 训练
- [ ] `python -m training.sft_train --dry-run --max-steps 2` CPU 自检通过
- [ ] 5 步探针：loss 有限且下行，nvidia-smi 峰值显存 < 15GiB
- [ ] 完整训练 3 epoch，loss 曲线正常无 NaN
- [ ] eval 1818 条（300 个未见过关卡）上 loss / 动作正确率达标
- [ ] checkpoint 只存 LoRA adapter（≈ 100MB），不存全量 8B

### P6 部署端到端
- [ ] 慢思考 + 快反应 + VLM + MCP + perception + action 全部注入 `ArknightsEnv`
- [ ] `run_episode()` 跑一局简单关卡（如 1-1），通关
- [ ] `live_state.push()` 正常工作，前端 `/ws/live` 收到真实帧
- [ ] 每步决策输出 reasoning + evidence 分级，可解释性面板非空

### P7 评估
- [ ] `env/reward.py` 批量跑分，出对局报告
- [ ] 对比 mock→真机、慢思考开/关、RAG 开/关
- [ ] 记录到 `docs/experiment_log.md`

---

## 六、上线红线（每步都检查）

- [ ] PRTS 爬取数据、游戏截图/素材、MAA 模板、视频/音频/抽帧（`data/video_raw`、`data/video_frames`）、
      权重、results **不进公开仓库**（.gitignore 已覆盖）
- [ ] 视频为第三方版权素材：只本地训练用，不分发媒体文件；SFT 中保留 UP 主来源与"第三方分析"标注
- [ ] MAA 仅作接口/坐标参考后自测重写，不分发其代码与资源；README 保留署名
- [ ] 所有 GPU 路径在真机跑通前都保留可回退的 mock，保证 CPU 冒烟始终绿
- [ ] `configs/training.yaml` 的 `model.torch_dtype` 改 float16 后再加载模型
- [ ] 毕设仓 `pointcloud-registration-detection` 与本仓 `arknights-llm-agent` 完全隔离，互不污染

---

## 七、相关文档索引

| 文档 | 内容 |
|------|------|
| `docs/v100_checklist.md` | 详细上线步骤（Step 1–7）+ SFT 精确执行手册（LoRA 配置/超参/显存预估/时间估算） |
| `docs/troubleshooting.md` | PointNet2 编译/CUDA 版本/OOM/数据格式/LiveState 线程安全等问题的现象/原因/修复 |
| `docs/architecture.md` | 整体架构（CV+VLM 双通道/慢快思考/知识图谱/MCP）+ 模块状态表 |
| `docs/setup.md` | 环境搭建详细步骤 |
| `docs/api.md` | 后端 API 完整文档（知识工具/对局日志/知识图谱/Dashboard 9 接口） |
| `docs/dashboard_design.md` | Dashboard 设计稿（六模块/API 设计/路由） |
| `docs/sft_data_quality.md` | SFT 数据质量报告（18080 条入训/黑话占比/切分） |
| `docs/project_plan.md` | 项目路线图 + 里程碑（CPU 侧完成清单 + V100 侧待办） |
| `configs/agent.yaml` | Agent 配置（模型名/dtype/超参） |
| `configs/training.yaml` | 训练配置（基座/LoRA/SFT/DPO 超参） |
| `configs/perception.yaml` | 视觉配置（坐标占位/YOLO/OCR 区域） |
