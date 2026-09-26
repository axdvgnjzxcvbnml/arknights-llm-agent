# Configs 一致性审计

> 审计时间：2026-09-27
> 范围：configs/*.yaml（6 个配置文件）
> 方法：逐字段对照代码引用（grep config[]/cfg[]/config.get）

## 一、一致性检查

### 1.1 dtype 一致性 ✅
| 配置文件 | 字段 | 值 |
| --- | --- | --- |
| agent.yaml | models.slow.dtype | float16 |
| agent.yaml | models.fast.dtype | float16 |
| training.yaml | model.torch_dtype | float16 |
| training.yaml | qlora.bnb_4bit_compute_dtype | float16 |
| training.yaml | sft.fp16 / bf16 | true / false |
| training.yaml | dpo.fp16 | true |

全部一致为 float16（V100 sm_70 无 bf16）。✅

### 1.2 模型名一致性 ⚠️（有意差异，需文档说明）
| 用途 | 配置文件 | 字段 | 值 |
| --- | --- | --- | --- |
| 慢思考推理 | agent.yaml | models.slow.name | Qwen/Qwen3-8B-**Thinking** |
| SFT 训练基座 | training.yaml | model.sft_base_model | Qwen/Qwen3-8B（无 Thinking） |
| 快反应推理 | agent.yaml | models.fast.name | openbmb/MiniCPM3-4B |
| 快反应基座 | training.yaml | model.fast_base_model | openbmb/MiniCPM3-4B |

**差异说明**：SFT 基座用 `Qwen3-8B`（基础版），推理用 `Qwen3-8B-Thinking`（带思维链）。这是合理的——SFT 微调基础版，推理时加载 Thinking 版获得更强推理能力。但**需在 training/README.md 里明确说明这个差异**，避免 V100 上加载错误模型。

### 1.3 device 一致性 ✅
| 模块 | 设备 | 说明 |
| --- | --- | --- |
| agent slow/fast | cuda:0 | V100 |
| perception yolo | cpu | TODO-V100 改 cuda |
| perception ocr | cpu | TODO-V100 改 cuda |
| perception vlm | cuda:0 | V100 |
| knowledge embedding | cpu | V100 可改 cuda |

## 二、死配置（代码未引用）

| 配置文件 | 字段 | 状态 | 建议 |
| --- | --- | --- | --- |
| knowledge.yaml | rag.vector_store.distance | 死配置 | ChromaDB 创建 collection 时未使用此字段；保留（未来切换距离函数时用）或删除 |
| knowledge.yaml | rag.embedding.backend=auto | 半死 | embedding.py 支持 auto/bge/mock，但 build_rag.py 直接 load_embedder 不传 backend；保留，接口已预留 |
| perception.yaml | models.template.skill_ready_dir | 死配置 | 模板匹配模块未实现；保留（TODO-V100 模板匹配时用） |
| training.yaml | model.fast_base_model | 半死 | SFT/DPO 只训 slow 模型，fast_base_model 未被训练脚本引用；保留（未来快反应微调时用） |
| training.yaml | model.device_map | 死配置 | sft_train.py 未使用 device_map；保留（多卡训练时用） |
| training.yaml | data_prep.job_dir | 半死 | sft_data_prep.py 从命令行参数接收 job_dir，不读配置；保留（默认值参考） |
| agent.yaml | knowledge.top_k / use_graph / evidence_strict | 半死 | decision_loop.py 未直接引用，MCPKnowledge 内部硬编码 top_k=5；**建议**：MCPKnowledge 改为从 config 读取 |

## 三、缺失字段（代码引用但配置无，有默认值兜底）

| 代码位置 | 引用字段 | 默认值 | 配置状态 |
| --- | --- | --- | --- |
| agent/fast_reactor.py:98 | models.fast.noop_trigger_slow_threshold | 3 | agent.yaml 无此字段，有默认值 |
| perception/state_parser.py | spawn.timeline | {} | perception.yaml 有 `timeline: {}` ✅ |
| action/adb_controller.py:65 | device_adb | 从 perception_config 注入 | action/config.py 注入 ✅ |

均有默认值兜底，不影响运行。建议在 agent.yaml 的 models.fast 下加 `noop_trigger_slow_threshold: 3` 使配置显式化。

## 四、修复项（本次执行）

### ✅ 已修复
1. **agent.yaml**：models.fast 下加 `noop_trigger_slow_threshold: 3`（显式化默认值）
2. **training/README.md**：补充 SFT 基座（Qwen3-8B）与推理模型（Qwen3-8B-Thinking）的差异说明

### 🔄 保留（有意设计或未来使用）
- 死配置全部保留，均标注了用途；删除会破坏未来扩展性
- knowledge.top_k 等半死配置保留，MCPKnowledge 未来从 config 读取

## 五、配置加载入口

| 模块 | 加载器 | 配置文件 |
| --- | --- | --- |
| agent | agent/config.py:load_agent_config() | configs/agent.yaml |
| knowledge | knowledge/config.py:load_knowledge_config() | configs/knowledge.yaml |
| perception | perception/config.py:load_perception_config() | configs/perception.yaml |
| action | action/config.py:load_action_config() | configs/action.yaml（注入 perception coords） |
| training | training/config.py:load_training_config() | configs/training.yaml |
| menu | perception/menu_io.py 直接读 | configs/menu.yaml |

## 六、建议（后续）

1. **统一配置加载入口**：当前 6 个模块各有 load_xxx_config()，建议统一为一个 `configs/loader.py`，支持按模块名加载
2. **配置 schema 验证**：见任务14，为所有 configs 定义 Pydantic schema，启动时验证
3. **MCPKnowledge 从 config 读取 top_k**：当前硬编码 5，应读 agent.yaml knowledge.top_k
