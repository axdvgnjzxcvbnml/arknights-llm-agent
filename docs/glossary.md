# 术语表（Glossary）

> 最后更新：2026-09-27
> 本术语表统一全项目文档和代码中的术语定义。

## 一、证据分级（Evidence Levels）

| 术语 | 定义 | 颜色标签 | 示例 |
| --- | --- | --- | --- |
| `fact` | 从 PRTS Wiki 结构化数据直接提取的事实 | 绿色 | 干员名、防御值、关卡敌情 |
| `retrieved` | RAG 检索到的相关文档，非事实判断 | 蓝色 | 攻略文本、干员背景故事 |
| `inferred` | 基于规则/数据推导的结论，非直接事实 | 橙色 | 克制关系（R1/R2/R3）、干员推荐 |
| `inferred:placeholder` | 凭经验拍脑袋的占位规则，待数据校准 | 橙色虚线 | 部署优先级排序 |
| `estimated` | 基于时间轴均匀估算的值，非实测 | 黄色虚线 | 敌人波次到达时间 |
| `cv` | 计算机视觉确认的实测值 | 青色 | YOLO 检测到的敌人位置 |
| `mock` | 测试用假数据，不代表真实 | 灰色 | MockOCRCostReader 返回的固定费用 |

## 二、Agent 架构术语

| 术语 | 定义 |
| --- | --- |
| 慢思考（Slow Thinker） | Qwen3-8B-Thinking，负责战略级决策，延迟 1-2 秒 |
| 快反应（Fast Reactor） | MiniCPM3-4B，负责即时操作，延迟 <200ms |
| 慢快桥接（Latent Bridge） | 将慢思考隐藏层投影到快反应输入空间，避免文字往返 |
| 决策循环（Decision Loop） | 截屏->解析->检索->决策->执行->记录的主循环 |
| 知识端口（Knowledge Port） | Agent 调用 MCP 工具/RAG/图谱的统一接口 |
| StepRecord | 单步决策记录，含状态/动作/reasoning/耗时/evidence |

## 三、感知层术语

| 术语 | 定义 |
| --- | --- |
| 快通道（CV Channel） | YOLOv8n + OCR + 模板匹配，目标 <50ms |
| 慢通道（VLM Channel） | Qwen3-VL/UI-TARS，负责局势理解，目标 2s/次 |
| SpawnTracker | 敌人波次时间轴追踪器，用关卡敌情表+计时推算敌人状态 |
| confirm_spawn | CV 检测到敌人确实出现时，将状态从 estimated 升级为 cv |
| GameState | 结构化游戏状态，含费用/干员/敌人/地图/技能冷却 |

## 四、知识库术语

| 术语 | 定义 |
| --- | --- |
| RAG | Retrieval-Augmented Generation，检索增强生成 |
| BM25 | 基于词频的关键词检索算法，与向量检索互补 |
| RRF | Reciprocal Rank Fusion，倒数排名融合，用于合并多路检索结果 |
| 知识图谱（Knowledge Graph） | NetworkX 构建的干员-技能-敌人-关卡关系图 |
| MCP | Model Context Protocol，LLM 工具调用协议 |
| chunk | RAG 切分后的文本块，200-500 字 |
| evidence 分级 | 见上文"证据分级"章节 |

## 五、克制规则（R1/R2/R3）

| 规则 | 触发条件 | 结论 | evidence |
| --- | --- | --- | --- |
| R1 高防克制 | 敌人 defense >= 阈值（默认800） | 术师/法术伤害干员克制 | inferred |
| R2 高法抗克制 | 敌人 magic_resistance >= 阈值（默认50） | 物理伤害干员克制 | inferred |
| R3 高速克制 | 敌人 move_speed >= 阈值（默认2.0） | 减速/控制干员克制 | inferred |

## 六、训练术语

| 术语 | 定义 |
| --- | --- |
| SFT | Supervised Fine-Tuning，监督微调 |
| DPO | Direct Preference Optimization，直接偏好优化 |
| LoRA | Low-Rank Adaptation，低秩适配微调方法 |
| QLoRA | Quantized LoRA，4bit 量化 + LoRA |
| 预 tokenize | 训练前将文本转换为 token ids，节省训练时的 tokenize 时间 |

## 七、其他

| 术语 | 定义 |
| --- | --- |
| MAA | MaaAssistantArknights，明日方舟助手，本项目参考其 ADB 控制层设计 |
| PRTS | prts.wiki，明日方舟中文维基百科 |
| 源石三档 | 立即可拿/短期可拿/长期可拿，用于抽卡决策的资源估算 |
| 干员本体 | 真实可抽取的干员，区别于召唤物/装置（弦惊、龙、幻影等） |
