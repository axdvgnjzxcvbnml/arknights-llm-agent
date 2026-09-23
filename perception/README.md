# perception —— 视觉解析

- `screen_capture.py`：ADB 截屏接口（MuMu 模拟器 `adb connect 127.0.0.1:7555`）
- `state_parser.py`：游戏状态解析
- `detector_yolo.py`：YOLOv8 干员 / 敌人检测（骨架 + mock，训练在 V100）
- `ocr_cost.py`：PaddleOCR 费用识别（骨架）
- `map_parser.py`：地图格子解析（可部署 / 已占用格子）
- `state_to_text.py`：结构化状态 → 自然语言文本（喂给 LLM）

第三批实现。GPU 推理标注 `# TODO-V100:`，CPU 侧全部可 mock。
