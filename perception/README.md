# perception —— 视觉解析（CV 快通道 + VLM 慢通道）

整体设计见 [`docs/architecture.md`](../docs/architecture.md) 第 3 节。快通道（YOLO/OCR/
模板/地图，目标 ≤50ms）输出结构化 `GameState`；慢通道（VLM，2s 一次）做局势理解与解释。

## 分层

| 文件 | 职责 | 第三批状态 |
|---|---|---|
| `config.py` | 读取 `configs/perception.yaml`（ADB/坐标/模型/波次） | 完成 |
| `schemas.py` | 视觉结构化状态 Pydantic 契约（`GameState` 等） | 完成 |
| `screen_capture.py` | ADB 截屏（MuMu）+ `MockScreenCapture` 合成帧 | ADB 真实接口 + mock |
| `state_parser.py` | 组装 `GameState`、`SpawnTracker` 波次推算、`MockStateParser` | 完成（CV 读数注入） |
| `ocr_cost.py` | PaddleOCR 费用识别 + 两帧一致性容错 | 真实接口（延迟装 paddle）+ mock |
| `map_parser.py` | 地图格子解析 + 开局布局缓存 | 真实骨架（NotImplementedError）+ `MockMapParser` |
| `detector_yolo.py` | YOLOv8 检测骨架 + `confirm_spawn` 波次确认 + `MockDetector` | 真实 detect TODO-V100，mock 左侧 3 重装 |
| `vlm_analyzer.py` | VLM 慢通道（截图+GameState→`VLMAnalysis`） | 真实 analyze TODO-V100（Qwen3-VL/UI-TARS）+ `MockVLMAnalyzer` |
| `state_to_text.py` | GameState(+VLM)→中文状态报告，分区固定+证据分级 | ✅ 真实实现（纯 CPU，喂 LLM） |

## 敌情第一版：波次推算 + 视觉确认

不做实时敌人检测：开局用 MCP `query_stage` 取敌情表，`SpawnTracker` 按时间推算当前波次
（有标注用标注 `annotated`，否则均匀估算 `estimated`），YOLO 只在 `confirm_spawn` 上确认
"敌人是否已出现"。PRTS 敌情表不含秒级时间轴，估算时间需真机录制校准（见 architecture.md 第4节）。

确认与升级的衔接：

```python
ok = detector.confirm_spawn("碎骨", frame)          # bool，只看 coords.enemy_confirm_region
plan, presence = SpawnTracker.update(plan, elapsed, confirmations={"碎骨": ok})
# ok=True 时该敌人由 timer:estimated 升级为 cv
```

YOLO 训练数据（V100）：PRTS 敌人裁剪图（仅本地训练，不入库）+ MuMu 录屏抽帧人工标注的
YOLO 格式数据集，基座 yolov8n。

## VLM 慢通道

`VLMAnalyzer.analyze(frame, state) -> VLMAnalysis`，字段：`situation`（局势理解）、
`strategic_advice`（战略建议）、`confidence`、`evidence[]`（带来源与 fact/retrieved/
inferred 标记）、`risks`。VLM 结论自身恒 `level=inferred`；`due()` 按 `models.vlm.interval_sec`
做 2s 节流，不阻塞快通道。V100 上填 Qwen3-VL-8B 或 UI-TARS-7B。

**快慢通道是分工不是替代**：快通道 <50ms 负责实时读数与微操依据；VLM 两次分析之间的
间隙，决策由 CV 状态 + SpawnTracker 波次推算撑住，不等 VLM（详见 architecture.md 第3节）。

## 状态报告（state_to_text）

`state_to_text(state, analysis=None)` 纯 CPU 渲染固定分区中文报告：关卡/对局时间/波次
时间轴来源、费用（含 稳定/存疑/未读到 标记）与耐久/部署、可用干员、已部署与技能、
敌情波次（每条带 [CV确认]/[计时估算]/[标注时间轴]）、可部署格子、VLM 局势/建议/风险，
末尾【证据分级】汇总 `fact / retrieved / inferred / cv / estimated / annotated / mock`。
空状态安全返回占位文本。

## 坐标与素材

UI 坐标在 `configs/perception.yaml` 的 `coords`（占位，真机阶段**自行测量或参考后重写**）；
**仓库不提交 MAA 模板与游戏素材**——模板图片由使用者自行从 MaaAssistantArknights 获取，
经 `models.template.skill_ready_dir` 等配置接入。坐标布局思路参考
[MaaAssistantArknights](https://github.com/MaaAssistantArknights/MaaAssistantArknights)，谨致谢忱；
若直接附带其文件需先逐文件核对许可。合成 mock 数据存 `data/mock/`。

## 费用 OCR 容错

`BaseCostReader.read()` 维护上一帧读数：费用只增不减，相邻两帧不一致 → `CostStatus.state=
uncertain`（confidence≤0.4），调用方"先别据此决策"；本帧读不到数字 → `state=missing`
（保留上一稳定值仅供参考）；重新连续一致后恢复 `ok`。

## import 安全

`import perception` 只拉起 numpy/yaml/pydantic；torch / ultralytics / paddleocr / VLM 在
对应方法内延迟导入，CI 与无 GPU 环境安全。

## 测试

```bash
python -m pytest tests/test_perception.py -v
```
