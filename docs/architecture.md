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
- `confirm_spawn(frame, expected_enemy, roi)`：波次出现确认（第一版主用）。

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
