# agent —— LLM Agent 核心

慢思考 / 快反应 / 桥接 / 主决策循环，以及 Prompt 模板与结构化输出定义。

- `decision_loop.py`：主决策循环（截屏→解析→检索→决策→执行→记录，逐步日志）
- `slow_thinker.py`：慢思考模型（Qwen3-8B-Thinking，V100；CPU 侧 mock 实现）
- `fast_reactor.py`：快反应模型（MiniCPM 级小模型，TODO-V100）
- `latent_bridge.py`：慢→快桥接（TODO-V100）
- `prompt_templates/`：system / decision / reasoning / self_reflect 模板
- `output_schema.py`：Pydantic 结构化输出（reasoning / action / confidence / knowledge_used）

第五批实现。本目录所有 GPU 相关代码标注 `# TODO-V100:`。
