# 架构说明（architecture）

> 状态：第三批（视觉解析）落地时建立。本文档描述目标架构与当前实现边界；
> 标注 `TODO-V100` 的部分只在 CPU 侧提供骨架与 mock，真实推理在 V100 完成。

## 1. 项目定位

一个"能看、能想、能打、能解释"的明日方舟 AI Agent：

- **不用 RL**。决策来自 LLM Agent + RAG + 知识图谱 + MCP 工具；奖励模块只用于离线评估。
- **能看**：CV 快通道解析结构化状态，VLM 慢通道做局势理解。
- **能想**：慢思考模型（Qwen3-8B-Thinking）结合检索知识做战略决策，快反应模型做即时操作。
- **能打**：动作层经 ADB 操作 MuMu 模拟器。
- **能解释**：每步决策输出 `reasoning`、`action`、`confidence`、`knowledge_used`。

## 2. 端到端闭环

```
                         ┌─────────────── 知识库（离线构建，CPU）──────────────┐
                         │ PRTS 爬虫 → JSON → RAG(bge+Chroma) / 知识图谱(NX)    │
                         │              └─ MCP 工具（fact/retrieved/inferred）  │
                         └───────────────────────────┬─────────────────────────┘
                                                     │ query_stage / search_guide /
 游戏截图 ┌──────────┐ 结构化 GameState(JSON)        │ recommend_operators
────────▶│ 视觉感知  │──────────────┐                ▼
 (MuMu/  │ CV + VLM  │              │        ┌────────────────┐
 ADB)    └──────────┘              ├───────▶│   LLM Agent    │ reasoning + action
     ▲                              │        │ 慢思考/快反应   │ + confidence + 引用
     │ ADB 点击/拖拽                │        └───────┬────────┘
     └────────────── 动作执行 ◀─────┴────────────────┘
                     (action_executor → ADB)
```

主循环（第五批 `agent/decision_loop.py` 落地）：
**截屏 → 解析（CV/VLM）→ 知识检索（MCP）→ LLM 决策 → 执行动作 → 记录/反思**。

## 3. 视觉感知：CV + VLM 混合双通道（本批核心）

```
游戏截图
  │
  ▼
┌───────────────────────────────────────────┐
│ 快通道 (CV, 目标 ≤50ms/帧)                 │
│  YOLOv8n …… 敌人/干员/物体检测             │
│  PaddleOCR …… 费用/技力/冷却数字识别       │
│  模板匹配 …… 技能按钮就绪/高亮状态         │
│  地图解析 …… 可部署/已占用格子             │
│  输出: 结构化状态 (GameState, JSON)        │
└───────────────────────────────────────────┘
  │ 结构化状态（轻量、确定、低延迟）
  ▼
┌───────────────────────────────────────────┐
│ 慢通道 (VLM, 目标 ≤2s 触发一次)             │
│  输入: 游戏截图 + CV 结构化状态            │
│  任务: 局势理解 / 异常确认 / 战略建议 /     │
│        可解释推理（自然语言）               │
│  输出: 战略级判断 + 解释（不直接做微操）     │
└───────────────────────────────────────────┘
```

**为什么双通道**：纯 VLM 延迟高、数字/格子识别不稳；纯 CV 能读数却不懂局势。
快通道保证"看得快、读得准"，慢通道保证"看得懂、能解释"。Agent 的即时操作只依赖
快通道 JSON；慢通道结论作为高一层的战略上下文，按 2s 节奏刷新。

**两者是分工不是替代**：快通道负责实时响应（<50ms 的检测/读数/微操决策依据），
VLM 慢通道负责战略级理解（约 2s 一次的局势判断与解释）。VLM 尚未产出或两次分析之间的
间隙，决策由 **CV 结构化状态 + SpawnTracker 波次推算**撑住，不等 VLM；VLM 结果到达后再
用于修正战略方向，绝不能让 2s 的慢通道阻塞每帧的即时操作。

### 3.1 延迟预算（目标，V100）

| 环节 | 通道 | 预算 |
|---|---|---|
| ADB 截屏 | - | ~100ms（含传输） |
| YOLOv8n 检测 | 快 | ≤30ms |
| OCR 费用/冷却 | 快 | ≤15ms |
| 模板匹配（技能按钮） | 快 | ≤5ms |
| 地图格子解析 | 快 | ≤5ms（ROI 内） |
| **快通道合计** | 快 | **≤50ms（不含截屏）** |
| VLM 局势理解 | 慢 | ≤2s，周期触发，不阻塞快通道 |

CPU 沙箱不做性能验证；mock 全链路只验证接口与时序契约。

## 4. 第一版敌情：波次推算 + 视觉确认（不做实时敌人检测）

第一版**不**依赖 YOLO 实时识别每个敌人，改用"关卡敌情表 + 计时推算"：

1. 开局用 MCP `query_stage(stage_id)` 取本关敌人/波次表（PRTS fact）。
2. `SpawnTracker` 以关卡开始时间为零点，按配置的波次/出场时间表推算"当前应到第几波、
   场上应有哪些敌人"。
3. YOLO 此时只做轻量**确认**：在预测出现的 ROI 上判断"敌人是否已出现/漏兵/异常增员"，
   并回写校正时间轴。检测置信度低时不硬判，交给慢通道 VLM 复核。

接口在 `perception/detector_yolo.py` 预留：
- `detect(frame, roi=None)`：通用目标检测（TODO-V100，训练后填充）；
- `confirm_spawn(enemy_name, frame)`：波次出现确认（第一版主用）。返回 `True` 表示该敌人经 CV 确认已出现（把 `SpawnTracker` 中对应状态从 `estimated` 升级为 `cv`），`False` 表示未检测到；ROI 由 `configs/perception.yaml` 的占位坐标给出（真机校准）。

> 注：PRTS 关卡页敌情表给的是敌人种类/数量/级别/数值，**不含精确出场秒级时间轴**。
> 波次时间表来自 `configs/perception.yaml` 的手工/录制标注（`spawn_timeline`），
> 缺标注时退化为"按总数量均匀估算"，并在状态里标 `timing_source=estimated`，
> GameState.notes 中明确写"估算值"。
> 这是已知的不确定来源，不假装精确。
>
> **真机阶段第一步：先逐关录制真实敌人出场时间轴**（用带时间戳的录像/视觉确认打点），
> 回填 `spawn.timeline` 把 `estimated` 替换为 `annotated`，用它校准波次推算；
> 在校准完成前，Agent 不得仅凭估算波次做高风险决策。

## 5. 坐标复用：MAA 资源（配置驱动，不内置素材）

干员卡牌位、技能按钮位、地图格子等 UI 坐标可参考 MAA（MaaAssistantArknights）资源布局，
但按以下边界处理：

- 所有坐标/ROI 放在 `configs/perception.yaml` 的 `coords` 段（按分辨率/主题分档），
  代码只读配置，不硬编码像素。
- 坐标**自己测量或参考 MAA 后重写**，不直接拷贝其资源文件；
- **不把 MAA 的模板图片/脚本或任何游戏素材 vendoring 进仓库**。模板图片由使用者自行从
  MAA 获取，并在本地经配置 `models.template.skill_ready_dir` 等路径接入。
- 在 README/相关文档中**署名 MaaAssistantArknights 项目**；若日后要直接附带其文件，
  需先逐文件核对许可（代码与资源许可证可能不同）。
- CPU 侧 `coords` 只放占位/合成值，保证 mock 链路可跑。

## 6. 知识引用与 evidence 语义

Agent 引用知识时必须带 evidence，三值语义：

| evidence | 含义 | 来源 |
|---|---|---|
| `fact` | PRTS Wiki 结构化事实 | query_operator/skill/enemy/stage |
| `retrieved` | RAG 检索到的**参考资料**，非事实判断，需核实 | search_guide |
| `inferred` | 规则/模型**推断**，非官方结论 | recommend_operators、VLM 战略判断 |

视觉结构化状态也带来源标记：CV 读数标 `cv`（可能误识别），波次估算标 `estimated`，
VLM 判断标 `vlm/inferred`，避免下游把"机器看到的"当成绝对事实。

## 7. Mock 全链路（CPU 冒烟，无 GPU/模拟器/PRTS 运行时依赖）

```
MockScreenCapture(合成帧)
   → MockStateParser（合成 GameState：费用/手牌/敌人/地图/技能）
      → state_to_text（真实实现：GameState → 中文状态描述）
```

- 合成帧/假状态由程序生成，**不含任何真实游戏截图或 PRTS 素材**（存 `data/mock/`）。
- 分层：`perception/schemas.py`（Pydantic 契约）/ `*` 真实或骨架 / mock 实现分离；
  `import perception` 不拉起 torch/paddle/ultralytics（重依赖在方法内延迟导入）。

`scripts/run_smoke.sh` 现共 **4 段**，全部为 CPU mock，不依赖 GPU/模拟器/爬虫数据：

1. **视觉**：`smoke_perception.py`——截屏→OCR/地图→状态解析（含敌情确认）→state_to_text→VLM；
2. **Agent**：`smoke_agent.py`——状态→知识检索→慢思考→桥接→快反应→执行→反思；
3. **环境**：`smoke_env.py`——`reset → step → is_done`，跑完整两局并出对局报告；
4. **视频信息提取**：`smoke_video.py`——下载→抽帧→口播(ASR mock)→图表(VLM mock)→对齐→SFT。

## 8. 模块状态

**第三批视觉骨架已完成**（CPU 侧 mock 全链路可跑，见 `scripts/run_smoke.sh`；
`tests/test_perception.py` 45 个用例）。

| 模块 | 第三批状态 |
|---|---|
| `screen_capture.py` | ✅ ADB（exec-out/pull）真实接口 + MockScreenCapture 合成帧 |
| `state_parser.py` | ✅ GameState 组装 + SpawnTracker 波次推算 + MockStateParser |
| `ocr_cost.py` | ✅ PaddleOCR 真实接口（延迟加载）+ 两帧一致性容错 + mock |
| `map_parser.py` | ✅ 真实 `_detect` 留 TODO + 开局布局缓存 + MockMapParser |
| `detector_yolo.py` | ✅ YOLO 真实 detect TODO-V100 + `confirm_spawn` 预留 + MockDetector |
| `vlm_analyzer.py` | ✅ VLM 真实 analyze TODO-V100（Qwen3-VL/UI-TARS）+ 2s 节流 + Mock |
| `state_to_text.py` | ✅ **真实实现**（纯 CPU，GameState+VLM→中文报告，含证据分级） |
| `schemas.py` | ✅ 视觉结构化状态 Pydantic 契约（GameState/VLMAnalysis） |
| `configs/perception.yaml` | ✅ ADB/分辨率/坐标占位（含 enemy_confirm_region 占位标注）/波次/模型 |
| `scripts/run_smoke.sh` | ✅ 视觉 mock 全链路，输出游戏状态报告到 `results/`（gitignore） |
| `scripts/check_env.sh` | ✅ 最小环境检查（第八批扩 GPU 侧） |

### 第四批：动作执行骨架（已完成）

**自写轻量 ADB 封装，不使用 maa-framework/其 AGPL 绑定，项目保持 MIT。** 高层 Action
编译成 tap/swipe/wait 原语经 controller 下发；单动作失败只记录不中断整段序列。
CPU 侧 MockActionExecutor 走通编排（run_smoke `[7/7]`，`tests/test_action.py` 23 项）。

| 模块 | 状态 |
|---|---|
| `action/adb_controller.py` | ✅ ADBController（MuMu 7555，connect/在线预检/tap/swipe/key/screencap，超时/离线/失败明确不静默）+ MockADBController（记日志） |
| `action/action_space.py` | ✅ Pydantic `Action`(deploy/skill/retreat/wait 严格联合校验)+`ActionPlan`+结果模型+`GridConverter`（格子/卡槽→像素，读配置） |
| `action/action_executor.py` | ✅ compile/execute 分离，resolver 定位干员，动作间等待，失败不中断；MockActionExecutor 不真 sleep |
| `configs/action.yaml` + `action/config.py` | ✅ 时序/卡槽/撤退占位；合并 perception 的 coords（坐标单一来源） |
| 真机手势/坐标 | ⏳ 占位（部署拖放朝向、技能选中、撤退按钮、等距斜切），`TODO 真机校准`，参考 MAA 后自测量 |

### 第五批：LLM Agent 核心（已完成）

**LLM Agent + RAG + 知识图谱/MCP，不用 RL。** 决策闭环纯 CPU 编排，组件依赖注入，
V100 换 slow/fast/bridge 三个模型的真实实现即可，循环代码不改；**但若要启用 latent bridge
（神经隐状态投影），还需额外调整 `think()` 返回值**：让慢模型在 `AgentDecision.hidden_state`
里回填最后一层隐状态——该字段默认 `None`（且不进 model_dump/JSON/日志），缺省时桥接层
`project()` 自动退化为"文字桥接 fallback"，因此在文字桥接跑通前不需要动 think()。
CPU mock 跑通"感知→知识→慢思考→桥接→快反应→执行→反思"（run_smoke 第 2 段，
`tests/test_agent.py`）。

| 模块 | 状态 |
|---|---|
| `agent/output_schema.py` | ✅ Reasoning/AgentDecision/BridgeState/FastCommand/Reflection/StepRecord/DecisionLog/KnowledgeBundle/Citation；动作复用 action.ActionPlan（不重复定义） |
| `agent/slow_thinker.py` | ✅ SlowThinkerQwen3 `# TODO-V100`（Qwen3-8B-Thinking，含 prompt 组装）+ MockSlowThinker（状态感知规则决策）+ reflect |
| `agent/fast_reactor.py` | ✅ FastReactorMiniCPM `# TODO-V100`（<150ms）+ MockFastReactor（费用/手牌/空格/技能就绪即时裁剪，全拦退化为 wait） |
| `agent/latent_bridge.py` | ✅ 神经投影 `# TODO-V100`（省文字往返）+ MockLatentBridge（确定性伪向量 256 维 + 意图 hint）；`project()` 统一判 `decision.hidden_state`：有值走神经投影（V100），无值走文字桥接 fallback（两条路径 BridgeState 同形） |
| `agent/decision_loop.py` | ✅ 纯 CPU 主循环 + Mock/RAGGraph 知识端口 + 可演进 MockPerception + build_mock_loop + 可解释日志渲染落盘 |
| `agent/prompt_templates/` | ✅ system/decision/reasoning/self_reflect，`{{TOKEN}}` 替换，全程 evidence 分级约束 |
| `configs/agent.yaml` | ✅ 模型/设备/桥接维度/检索 top_k/循环步数/延迟预算 |
| 可解释性 | ✅ 每步 reasoning(依据/取舍/风险)+knowledge_used(evidence分级)+confidence+reflection；日志 `results/agent_decision_log.txt`（gitignore） |
| 真实模型推理 | ⏳ `# TODO-V100`：Qwen3-8B-Thinking / MiniCPM3-4B（`openbmb/MiniCPM3-4B`，HF 已核实） / 慢快隐状态投影 |

### 第六批：环境封装（已完成）

**调度接口而非 RL Gym：统一封装"看→想→做→再看"，不产生梯度、不用于训练。** 感知/执行/
Agent 组件依赖注入，V100 接真实模拟器时只换注入、环境代码不改。CPU mock 用 Gym 风格接口
跑完整两局（run_smoke 第 3 段，`tests/test_env.py` 14 项）。

> **编排入口约定（两条路径，语义必须一致）**
> - `agent/decision_loop.py`（`DecisionLoop` / `ak-agent`）是**调试与 mock 演示入口**：逐步
>   打印详细决策日志，便于开发期观察"感知→检索→慢思考→桥接→快反应→执行→反思"。
> - `env/arknights_env.py`（`ArknightsEnv.run_episode()`）是**唯一生产入口**：负责整局
>   reset/step/终局判定、奖励、对局报告与落盘，前端/评估/V100 真机都走它。
>
> 两条路径当前各自编排同一组组件。**修改任一路径的编排语义（步骤顺序、知识端口、计划
> 归一化、执行后状态回写等）时，必须同步检查并更新另一处**，避免调试链路与生产链路漂移；
> 后续可把公共的单步编排抽成一个共享函数（待办，M9 暂不重构）。

| 模块 | 状态 |
|---|---|
| `env/arknights_env.py` | ✅ ArknightsEnv：reset/step/get_state/is_done/get_log/close + run_episode；coerce_plan 接收 Action/ActionPlan/FastCommand/列表；EnvStep/EpisodeLog；render_episode_report；win/defeat/timeout/aborted 判定 |
| `env/reward.py` | ✅ 评估奖励（**非训练**）：通关+100 / 漏怪-10每点 / 费用溢出-1每秒；EpisodeReward 逐帧累计、RewardBreakdown 明细；RewardConfig 权重可注入 |
| `env/mock_env.py` | ✅ ScriptedPerception（叠加通关/生命归零终局）+ build_mock_env/run_mock_episode：10 步通关(+100) / 3 步失败(漏3点,-30) |
| 对局报告 | ✅ 每步状态/决策理由/证据/动作结果/奖励/耗时 + 汇总，落 `results/episode_report_{win,lose}.txt`（gitignore） |
| 真机对接 | ⏳ 注入真实 perception(ADB+CV) 与 executor；通关识别 `is_cleared()` 待真机用结算画面视觉判定（当前 mock 脚本化） |

### 第七批：训练模块（SFT 数据准备已完成；训练骨架待 V100）

**CPU 只做数据准备与脚本骨架，不在沙箱真实训练。** SFT 数据从 MAA 作业时间轴 + PRTS
语料反推 question/answer；理由恒标 `inferred:timeline_reconstructed`，不冒充专家原话。

| 模块 | 状态 |
|---|---|
| `training/sft_data_prep.py` | ✅ CPU 真实：解析 maa-copilot 子集(部署/技能/撤退)、前缀已部署状态反推、PRTS 事实拼接(fact)、理由(inferred)、未知动作跳过、无 PRTS 自动降级、JSONL+train/eval 切分；样例 `data/mock/maa_job_3-8.json` |
| `configs/training.yaml` / `training/config.py` | ✅ 模型/LoRA/SFT/DPO/数据准备超参；V100 sm_70 标 fp16（bf16 不支持） |
| `training/sft_train.py` | 🟡 完整自定义训练循环（LoRA / AdamW / cosine warmup / fp16 autocast / `--dry-run` 自检），V100 路径已就绪；无 CUDA 或缺 torch 时显式 `# TODO-V100`，CPU 可 dry-run 跑通数据→tokenize→forward→loss→backward→保存 |
| `training/dpo_train.py` | ⏳ 骨架 `# TODO-V100`：偏好对读取校验真实(prompt/chosen/rejected)；DPOTrainer 待 V100 |
| 真实训练 | ⏳ `# TODO-V100`：Qwen3-8B LoRA SFT / DPO。PointNet2 属毕设 pointcloud 仓，本项目不编译；V100 首步只做环境检查（见 `v100_step1_setup.sh` / v100_checklist） |

### 第八批：脚本与文档（已完成）

**CPU 侧最后一批：9 个一键脚本把"装环境→建库→V100 上线"串成可复现流水线。**
所有脚本开头做前置检查、结尾打印"下一步"；除 V100 专属步骤标 `# TODO-V100` 外无悬空 TODO。
V100 脚本带统一 GPU 门禁：无 CUDA 时 step2/3/4 以退出码 3 安全中止（不做假训练），step1 只检查
（无 GPU 仅告警），step5 在任意机器先跑 mock 评估基线。`tests/test_scripts.py` 固化语法/门禁/脚注。

| 脚本 | 状态 |
|---|---|
| `scripts/setup_env.sh` | ✅ 安装 requirements / `--minimal` / `ARK_SKIP_PIP=1` 仅查版本；打印关键库版本与 torch.cuda |
| `scripts/crawl_prts.sh` | ✅ `[operator\|enemy\|stage\|all] [limit]`，前置校验 requests/bs4 与联网，默认 50/50/20，透传 ARK_FORCE |
| `scripts/build_rag.sh` | ✅ 前置校验 chromadb/sentence-transformers 与 prts_raw 非空；`ARK_REBUILD=1` 全量重建，否则 upsert |
| `scripts/build_graph.sh` | ✅ 前置校验 networkx 与语料；构建并确认 GraphML 落盘 |
| `scripts/v100_step1_setup.sh` | ✅ 只检查环境（GPU/CUDA/sm_70/peft/trl/adb），明确**不编译 PointNet2（属毕设仓）** |
| `scripts/v100_step2_train_vision.sh` | ⏳ GPU 门禁 + `# TODO-V100` 视觉训练清单（YOLO 数据/训练、confirm_spawn、坐标与时间轴校准） |
| `scripts/v100_step3_sft.sh` | 🟡 先 CPU 跑 sft_data_prep（真实），再 GPU 门禁；sft_train 现按设计抛 `# TODO-V100` |
| `scripts/v100_step4_deploy_agent.sh` | 🟡 知识库产物检查→mock 回归→GPU 门禁；列出 adb/MCP/模型加载/组件注入清单 `# TODO-V100` |
| `scripts/v100_step5_eval.sh` | 🟡 任意机器跑 mock 评估基线（reward 口径）；真机批量评估 `# TODO-V100`（v100_checklist Step6） |
| `docs/experiment_log.md` | ✅ 实验记录模板（提交/环境/配置/指标/结论/产物/备注）+ mock 基线首条 |
| `docs/project_plan.md` | ✅ 路线图：阶段0（批1–8）完成清单、阶段1 V100 Step1–5 待办、阶段2 扩展、边界 |

## 9. 视频信息提取（第十四批，离线 SFT 数据支线）

面向攻略视频（首批 UP 主「血狼破军」），把**口播（分析逻辑）**与**画面图表（Excel 数据表 /
DPS 对比 / 强度榜）**两路信息提取成 SFT 训练对。它是离线数据生产线，不在实时对战闭环里，
不参与 Agent 在线推理。

```
yt-dlp 下载(视频+wav)
  → ffmpeg 抽帧（interval 固定间隔 / scene 场景切换；manifest 记时间戳）
  → ASR 口播转写（Whisper，# TODO-V100）  ┐
  → VLM 读图表（Qwen3-VL/UI-TARS，# TODO-V100）├─ 两路都带时间戳
  → aligner 时间轴就近对齐（区间包含优先，否则中点就近，超容差不强行配）
  → structurer 转 question/answer（每条带 BV号+画面/口播时间戳）
```

- **分层与轻量**：`import video_extract` 只用标准库 + pyyaml，不拉起 torch/transformers/
  numpy/whisper；yt-dlp/ffmpeg 走子进程、ASR/VLM 在方法内延迟导入。CPU 沙箱用 `Mock*`
  实现跑通全链路（run_smoke 第 4 段，`tests/test_video_extract.py` 48 项）。
- **合规**：视频/音频/抽帧只写 `data/video_raw/`、`data/video_frames/`（均 gitignore），
  仓库不含任何媒体；抓取默认限速 + 请求间隔 + 单次批量上限 + robots 校验。
- **证据分级**：画面数字 `retrieved:video_frame`、口播观点 `retrieved:video_audio`
  （均为 UP 主第三方分析，参考资料而非 PRTS 事实），时间戳就近关联 `inferred:timestamp`；
  answer 附第三方分析免责说明，`meta` 强制带 BV 号与时间戳，便于回溯。

### 第十四批：视频提取骨架（已完成）

| 模块 | 状态 |
|---|---|
| `video_extract/downloader.py` | ✅ yt-dlp CLI 封装：单视频下载+wav 音轨+info.json→VideoMeta；UP 主 `--flat-playlist` 列表；限速/指数退避/robots/断点续爬；MockDownloader 只落 meta |
| `video_extract/frame_extractor.py` | ✅ ffmpeg `fps=1/N` 与 `select=gt(scene)`（showinfo 取 pts_time）+ manifest；FFmpeg/ffprobe 缺失明确报错；MockFrameExtractor 时间戳占位（placeholder，不造假图） |
| `video_extract/transcriber.py` | ⏳ WhisperTranscriber 骨架 `# TODO-V100`（faster-whisper large-v3，cuda/float16）；MockTranscriber 固定带时间戳口播；build_transcriber 工厂 |
| `video_extract/chart_reader.py` | ⏳ VLMChartReader 骨架 `# TODO-V100`（Qwen3-VL/UI-TARS，表格/榜单→JSON）；MockChartReader 把数据/强度榜锚到最近抽帧时间戳 |
| `video_extract/aligner.py` | ✅ **CPU 真实**：区间包含优先→中点就近→超容差判 unmatched；纯函数 |
| `video_extract/structurer.py` | ✅ **CPU 真实**：对齐对→question/answer（table/tier 分化）+ BV/时间戳 + retrieved/inferred 证据 + 第三方免责；JSONL 落 `data/sft_data/` |
| `video_extract/config.yaml` | ✅ UP 主 UID=267766441（血狼破军，第十五批填入）/限速/抽帧/ASR/VLM 模型/对齐容差/证据键/`categorize` 分类段（`allowed_categories`、arknights/endfield 关键词） |
| 视频分类过滤（第十五批） | ✅ `categorize_video` 优先级 **endfield > arknights > other**（标题+标签、大小写不敏感；"明日方舟终末地"判 endfield 排除，防 SFT 污染）；下载前剔除 + info.json 真实 tags 复核双保险；只有 `allowed_categories`（默认仅 arknights）进抽帧/转写/结构化；冒烟演示放行 1 条明日方舟、排除 1 条终末地 |
| `scripts/smoke_video.py` + run_smoke | ✅ run_smoke 第 4 段 mock 全链路，报告落 `results/video_extract_report.txt`（gitignore） |
| 真实抓取/ASR/VLM | ⏳ 联网机器跑 downloader（已填 UID，确认合规）；V100 切 asr/vlx backend 与模型（见 v100_checklist） |

## 10. 第十五批新增：源石台账 / 非对战菜单骨架 / 培养决策

| 模块 | 状态 |
| --- | --- |
| `knowledge/source_stone_tracker.py` | ✅ **CPU 真实**（纯标准库）：主线首通源石台账。从 `data/prts_raw/stages` 只收 `章节-序号` 主线关（全量 288 关，其中 105 关有突袭）；规则=普通首通 1 + 突袭首通 1（常量可配）。拆分已获得/剩余普通/突袭，单列被普通首通卡住的 `locked_raid_stages`，按章节排序给"接下来可刷"；`render_for_prompt` 给抽卡决策摘要（含计划抽数→合成玉缺口粗算，1抽=600玉、1源石≈180玉）。证据 fact:规则/进度、inferred:calculated。测试 `tests/test_source_stone.py` 10 项（无数据目录时真实语料用例 skip） |
| `agent/prompt_templates/gacha.md` | ✅ 抽卡**资源规划**提示词（非自动充值/抽卡）；`{{SOURCE_STONE_INFO}}` 等令牌，要求区分 fact/inferred、给保守/中性/激进三档、不鼓励充值 |
| `perception/login.py` `gacha.py` `shop.py` | ⏳ 状态解析骨架 + Mock：LoginState（登录/公告/每日签到）、GachaState（卡池/合成玉/源石/凭证/可否抽）、ShopState（每日免费/商品）。真实 `*ScreenParser.parse` 一律 `NotImplementedError("TODO-V100")`（OCR/模板/VLM 待真机） |
| `perception/menu_io.py` + `configs/menu.yaml` | ✅ 菜单配置加载；坐标**全部占位 -1、calibrated=false（待真机校准）**；真实执行器在未校准时拒绝盲点 |
| `action/menu_actions.py` | ✅ 16 个逻辑动作（登录/公告/签到 6、抽卡 6、商店 4）复用 ADBController；坐标从 menu.yaml 读不硬编码；`MenuActionExecutor` 未校准/占位即 fail 且零点击，`MockMenuActionExecutor` 记录逻辑动作供闭环。测试 `tests/test_menu_actions.py` 13 项 |
| `strategy/operator_development.py` | ✅ **CPU 真实、只决策不操作**：输入干员列表+材料库存+关卡需求 → 培养优先级排序+理由。因子=关卡职业/职能匹配 + 练度缺口 + 强度榜 tier + 材料是否齐备；未拥有但需要的单列 `unowned_relevant`。未接榜时全部 `inferred:placeholder_rule`，接入血狼破军 tier JSON 后命中项标 `retrieved:tier_list`（外部观点，非事实）。`load_tier_list` 缺文件静默退回占位。测试 `tests/test_operator_development.py` 9 项 |

- **证据红线**：源石台账的折算是 inferred、强度榜是 retrieved 外部观点，菜单 mock 状态为 mock；
  三者都不允许在 LLM 侧被当作账号实测事实。
- **第十五批回归**：全量 `263 passed / 2 skipped`；run_smoke 4 段全过；87 个受 git 跟踪的
  Python 文件 py3.8 AST 零语法错误。
