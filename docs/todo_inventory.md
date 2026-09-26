# TODO 清单（重新分类）

> 重新分类时间：2026-09-27
> 全仓库 TODO 总数：84（修正3个分类错误后，TODO-V100 从84降至81）

## 分类标准

- **V100 专属**：必须 GPU 才能完成（模型推理/训练/视觉检测）
- **CPU 可做**：不需要 GPU，只是没写或沙箱环境受限
- **待用户决策**：需要用户拍板的设计/方向选择

## 一、V100 专属（75 项）

### Agent 核心（21 项）
| 文件 | 数量 | 内容 |
| --- | --- | --- |
| agent/slow_thinker.py | 8 | Qwen3-8B 模型加载/推理/结构化输出解析 |
| agent/fast_reactor.py | 7 | MiniCPM3-4B 模型加载/推理 |
| agent/latent_bridge.py | 6 | 慢快隐藏层投影器真实实现 |

### 视觉感知（16 项）
| 文件 | 数量 | 内容 |
| --- | --- | --- |
| perception/vlm_analyzer.py | 7 | Qwen3-VL/UI-TARS 模型加载/推理 |
| perception/detector_yolo.py | 5 | YOLOv8n 训练/推理/confirm_spawn 真实实现 |
| perception/shop.py | 3 | 商店界面 OCR+模板真实识别 |
| perception/login.py | 3 | 登录/签到界面 OCR+模板真实识别 |
| perception/gacha.py | 3 | 抽卡界面 OCR+模板真实识别 |
| perception/ocr_cost.py | 1 | PaddleOCR 真实费用识别 |
| perception/screen_capture.py | 1 | 真实 ADB 截屏（MuMu 模拟器） |
| perception/state_parser.py | 1 | 真实游戏状态解析 |
| perception/menu_io.py | 1 | 菜单界面 IO 真实实现 |

### 训练（13 项）
| 文件 | 数量 | 内容 |
| --- | --- | --- |
| training/sft_train.py | 6 | LoRA SFT 训练循环真实实现 |
| training/dpo_train.py | 5 | DPO 偏好训练真实实现 |
| training/pre_tokenize.py | 2 | 预 tokenize（CPU 可做但沙箱内存受限） |
| training/__init__.py | 1 | 训练模块初始化 |

### 视频提取（9 项）
| 文件 | 数量 | 内容 |
| --- | --- | --- |
| video_extract/transcriber.py | 8 | Whisper ASR 模型加载/推理 |
| video_extract/chart_reader.py | 1 | VLM 读图表（已补完真实实现，TODO 为模型选择） |

### 知识库（4 项）
| 文件 | 数量 | 内容 |
| --- | --- | --- |
| knowledge/rag/embedding.py | 2 | bge-small-zh 真实 embedding（CPU 可做但沙箱网络受限） |
| knowledge/mcp_tools/server.py | 1 | MCP 服务端真实部署 |
| knowledge/graph/build_graph.py | 1 | 图谱构建优化 |

### API/其他（12 项）
| 文件 | 数量 | 内容 |
| --- | --- | --- |
| api/server.py | 2 | 训练 metrics 接真实数据 |
| api/live_state.py | 1 | 跨线程安全（已修复，TODO 过时待清理） |
| agent/output_schema.py | 1 | 输出 schema 扩展 |
| agent/decision_loop.py | 1 | 决策循环优化 |
| action/menu_actions.py | 1 | 菜单动作真实实现 |
| video_extract/__init__.py | 2 | 模块初始化 |
| 其他 | 4 | 分散在各模块 |

## 二、CPU 可做（6 项，已处理 3 项）

| # | 文件 | 内容 | 状态 |
| --- | --- | --- | --- |
| 1 | video_extract/downloader.py | yt-dlp 下载（无 GPU 依赖，标注错误） | 已修正为 TODO-CPU |
| 2 | video_extract/frame_extractor.py | ffmpeg 抽帧（无 GPU 依赖，标注错误） | 已修正为 TODO-CPU |
| 3 | knowledge/graph/visualize_graph.py | 图谱可视化（无 GPU 依赖，标注错误） | 已修正为 TODO-CPU |
| 4 | api/live_state.py | 跨线程安全 | 任务18已修复，TODO 过时待清理 |
| 5 | training/pre_tokenize.py | 预 tokenize | 沙箱内存受限，V100 上跑更快 |
| 6 | knowledge/rag/embedding.py | bge 真实 embedding | 沙箱网络受限，V100 上下载 |

## 三、待用户决策（3 项，均已拍板）

| # | 内容 | 决策 |
| --- | --- | --- |
| 1 | MAA 作业 K=1 是否增量补抓 | K=1，不增量 |
| 2 | PRTS 活动关卡是否爬取 | 暂不爬 |
| 3 | SFT 黑话 <1% 是否建白名单 | 保留，等 V100 训练后看 eval |

## 四、已完成的 TODO（本轮清理）

- 修正 3 个分类错误的 TODO-V100 标注（downloader/frame_extractor/visualize_graph）
- api/live_state.py 跨线程安全已在任务18修复（TODO 过时，待清理注释）
- video_extract/chart_reader.py 已补完真实实现（TODO 为模型选择，非骨架）

## 五、后续建议

1. V100 上线后按优先级处理：slow_thinker -> fast_reactor -> vlm_analyzer -> detector_yolo -> sft_train
2. 每次完成一个模块的 TODO，更新本清单
3. 考虑加 CI 检查：TODO-V100 数量不应增加（防止新代码引入未标注的 GPU 依赖）
