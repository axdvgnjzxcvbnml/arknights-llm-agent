# configs —— 配置文件

所有路径、模型名、超参数统一放这里，**代码中不硬编码**。

- `default.yaml`：全局默认配置
- `agent.yaml`：LLM Agent 配置（模型、温度、决策循环参数）
- `knowledge.yaml`：知识库配置（embedding 模型、Chroma 路径、Top-K）
- `perception.yaml`：视觉配置（ADB 地址、YOLO 权重、OCR）
- `training.yaml`：V100 训练配置（SFT / DPO 超参）

第一批仅建目录，各 YAML 随对应模块落地时创建。
