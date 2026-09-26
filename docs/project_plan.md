# 项目路线图（project_plan）

目标：做一个"能看、能想、能打、能解释"的明日方舟 AI Agent —— **LLM Agent + RAG + MCP，不用 RL**。
在简单关卡跑通「看 → 想 → 打 → 再看」闭环，再逐步扩展到肉鸽等模式。

里程碑口径：
- ✅ 已完成并通过验收 ｜ 🟡 CPU 骨架就绪、真机/GPU 待补 ｜ ⬜ 未开始
- 所有版权数据（PRTS 抓取、游戏截图、MAA 资源）与权重/产物均 **不入库**。

## 阶段 0：CPU 侧骨架与 mock 闭环（沙箱可完成）

| # | 批次 | 状态 | 交付物 |
|---|---|---|---|
| 1 | 仓库脚手架 | ✅ | 目录结构、配置驱动、CI 三 job、MIT、.gitignore（版权/产物）、六类 commit 前缀 |
| 2 | 知识库 | ✅ | PRTS 爬虫（限速/退避/断点）、批量入口（MediaWiki API）、RAG（bge-small-zh + ChromaDB，923 chunk）、NetworkX 图谱（fact/inferred 分级）、6 个 MCP 工具（fact/inferred/retrieved 分层） |
| 3 | 视觉解析 | ✅ | ADB/Mock 截屏、状态解析（SpawnTracker estimated→cv）、OCR 两帧一致性、地图缓存、YOLO/VLM 骨架（TODO-V100）、state_to_text 中文报告 |
| 4 | 动作执行 | ✅ | 自写轻量 ADB（保 MIT，不引 maa-framework）、Pydantic 动作空间/坐标转换、执行器（失败不中断）、Mock |
| 5 | LLM Agent | ✅ | output_schema、4 个 prompt 模板、慢思考/快反应/桥接骨架（TODO-V100）、纯 CPU 决策循环（六段延迟、决策日志、知识端口两档） |
| 6 | 环境封装 | ✅ | Gym 风格调度（非 RL）、依赖注入、StepRecord/对局报告、Mock 两局、reward（仅评估） |
| 7 | 训练准备 | ✅ | SFT 数据准备（MAA 作业→JSONL，CPU 真实）、SFT/DPO 脚本骨架（TODO-V100）、V100 清单 |
| 8 | 脚本与文档 | ✅ | 9 个一键脚本（前置检查/下一步提示/GPU 门禁）、experiment_log、project_plan、脚本单测 |
| 9 | 全量真实数据 | ✅ | PRTS 全量爬取+质量审计、真 bge 重建 RAG、全量图谱重建、MAA 作业站 2 万+ SFT 样本（K=1）（数据仅本地） |
| 10 | V100 训练准备 | ✅ | 按关卡维度无泄漏 9:1 切分、50 条质量抽查报告、V100 SFT 精确执行清单、CPU 小模型 1–2 step 预演 |
| 11 | 后端 API | ✅ | FastAPI：MCP HTTP 化、对局日志、知识图谱接口、CORS、API 单测与 docs/api.md |
| 12 | API 契约修复 | ✅ | episodes 列表/落盘、EpisodeLog 与 DecisionLog 合流、evidence 统一 {level,source}、reward/分页/文档修正 |
| 13 | web-kb 前端 | ✅ | 知识库浏览器方案 A：删除本地建图、只消费后端 API；mock 由后端真实代码生成；真实联调通过（Qwen 的 web/ 待并入） |
| 14 | 视频提取骨架 | ✅ | yt-dlp/ffmpeg 封装、Whisper/VLM 骨架（TODO-V100）、时间轴对齐与转 SFT（CPU 真实）、mock 全链路（48 测试） |
| 15 | 视频分类 + 源石台账 + 非对战菜单骨架 + 培养决策 | ✅ | 血狼破军 UID=267766441；终末地优先排除的视频分类过滤（只放行 arknights）；`source_stone_tracker` 首通源石台账+抽卡 Prompt；登录/签到/抽卡/商店 视觉(mock)+动作(占位坐标待校准)；`strategy` 练干员优先级（占位规则+tier 端口）。新增 47 测试，全量 263 passed/2 skipped |

CPU 阶段出口标准：`git clone` 后按 README 跑 `run_smoke.sh` 即全绿（含第 4 段视频提取 mock），mock 跑通完整闭环，import 不拉 GPU 栈。

## 阶段 1：V100 真机打通（对齐 docs/v100_checklist.md）

| 步骤 | 内容 | 状态 |
|---|---|---|
| Step1 | V100 环境检查（torch/CUDA、sm_70、依赖、adb）。**不编译 PointNet2**（属毕设 pointcloud 仓） | 🟡 脚本就绪（`v100_step1_setup.sh`） |
| Step2 | YOLOv8n 视觉训练 + confirm_spawn 接真实检测；**先录制真实波次时间轴**校准 SpawnTracker；校准占位坐标（cost_box/grid/卡牌/技能按钮/enemy_confirm_region） | ⬜ TODO-V100（`perception/detector_yolo.py`） |
| Step3 | SFT：LoRA 微调 Qwen3-8B-Thinking（fp16）；数据 `data/sft_data`；权重 `weights/` | ⬜ TODO-V100（`training/sft_train.py`） |
| — | DPO 偏好训练 | ⬜ TODO-V100（`training/dpo_train.py`） |
| Step4 | 部署：adb 连 MuMu、起 MCP、加载慢/快/VLM 模型、注入真实组件到 `ArknightsEnv`，先打简单关 | ⬜ TODO-V100（`agent/*`、`vlm_analyzer.py`） |
| Step5 | 真机端到端评估：批量对局 + reward 口径 + 结算画面 `is_cleared` 判定，结果入 experiment_log | ⬜ TODO-V100（`env/arknights_env.py`） |
| Step6 | 离线视频 SFT：UID 已填（血狼破军 267766441，分类只放行 arknights、终末地已排除），联网限速抓取后 V100 跑 Whisper 口播 + Qwen3-VL 图表，对齐后 `structurer` 增补视频 SFT（retrieved/inferred 证据，不入库媒体） | ⬜ TODO-V100（`video_extract/*`） |

真机阶段第一优先级（来自第三批结论）：**录制真实出怪时间轴**替换均匀估算，并据此校准占位坐标。

## 阶段 2：能力扩展（简单关稳定后）

- ⬜ 快/慢双通道联调：快通道 <50ms 实时响应，VLM 2s 一次战略理解，间隙由 CV+SpawnTracker 支撑；latent_bridge 神经投影落地。
- ⬜ 更多干员/关卡覆盖，RAG 与图谱增量更新（爬虫与建库分离已支持）。
- ⬜ 肉鸽（集成战略）等模式：地图/收藏品随机性的状态扩展。
- ⬜ 可解释性增强：决策日志可视化、知识引用溯源到 PRTS 页面（retrieved 不升级为事实）。

## 当前不做（边界）

- 不做 RL / 梯度训练（reward 仅用于评估）。
- 不 vendoring PRTS 数据、游戏素材或 MAA 资源；不引入 AGPL 的 maa-framework（ADB 层自写，保持 MIT）。
- 不在 CPU 沙箱做任何真实训练或 GPU 推理。
