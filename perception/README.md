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
| `ocr_cost.py` | PaddleOCR 费用/技力识别 | 骨架 + mock（TODO-V100） |
| `map_parser.py` | 地图格子解析 | 骨架 + mock |
| `detector_yolo.py` | YOLOv8 检测 + 波次出现确认接口 | 骨架 + mock（TODO-V100） |
| `vlm_analyzer.py` | VLM 慢通道 | 骨架 + mock（TODO-V100） |
| `state_to_text.py` | `GameState` → 中文状态文本（喂 LLM） | 真实实现（纯 CPU） |

## 敌情第一版：波次推算 + 视觉确认

不做实时敌人检测：开局用 MCP `query_stage` 取敌情表，`SpawnTracker` 按时间推算当前波次
（有标注用标注 `annotated`，否则均匀估算 `estimated`），YOLO 只在 `confirm_spawn` 上确认
"敌人是否已出现"。PRTS 敌情表不含秒级时间轴，估算时间需真机录制校准（见 architecture.md 第4节）。

## 坐标与素材

UI 坐标在 `configs/perception.yaml` 的 `coords`（占位，真机阶段对齐 MAA 布局）；
**仓库不提交 MAA 模板与游戏素材**，合成 mock 数据存 `data/mock/`。

## import 安全

`import perception` 只拉起 numpy/yaml/pydantic；torch / ultralytics / paddleocr / VLM 在
对应方法内延迟导入，CI 与无 GPU 环境安全。

## 测试

```bash
python -m pytest tests/test_perception.py -v
```
