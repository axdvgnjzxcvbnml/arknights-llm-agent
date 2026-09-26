# TODO 清单与分类

> 生成时间：2026-09-27
> 扫描范围：agent/ knowledge/ perception/ action/ env/ api/ training/ strategy/ video_extract/ scripts/ configs/
> 总计：90 个 TODO-V100 + 5 个真机校准 TODO + 若干文档待办

## 分类总览

| 类别 | 数量 | 说明 |
| --- | --- | --- |
| V100 专属（必须等 GPU） | 90 | 标注 `# TODO-V100`，涉及模型推理/训练/视觉检测 |
| 真机校准（需模拟器/真机） | 5 | 标注"TODO 真机校准"，涉及 ADB 坐标/拖放/地图解析 |
| 可立即做（CPU 侧能落地） | 3 | 过时注释清理、文档更新 |
| 待用户决策 | 2 | 见 docs/pending_decisions.md |

## 一、V100 专属 TODO（90 个，按模块分布）

### agent/（15 个）
- `slow_thinker.py`：Qwen3-8B 真实加载与推理（当前 mock）
- `fast_reactor.py`：MiniCPM3-4B 真实加载与推理（当前规则引擎）
- `latent_bridge.py`：隐藏层投影器真实实现（当前文字桥接 fallback）
- `decision_loop.py`：真实感知/执行接入（当前 mock 全链路）
- `output_schema.py`：模型输出校验增强

### knowledge/（12 个）
- `rag/embedding.py`：bge-small-zh 真实 embedding（当前 mock 随机向量）
- `graph/visualize_graph.py`：交互式可视化（PyVis）
- `mcp_tools/server.py`：MCP 标准服务端部署

### perception/（28 个）
- `detector_yolo.py`：YOLOv8n 真实推理（需训练数据+V100 训练）
- `vlm_analyzer.py`：Qwen3-VL/UI-TARS 真实推理
- `ocr_cost.py`：PaddleOCR 真实识别（CPU 可装但沙箱未装）
- `screen_capture.py`：ADB 真实截屏（需模拟器）
- `state_parser.py`：真实游戏状态解析
- `gacha.py` / `login.py` / `shop.py` / `menu_io.py`：菜单视觉解析

### action/（3 个）
- `adb_controller.py`：真实 ADB 连接（需模拟器）
- `menu_actions.py`：菜单动作执行

### api/（2 个）
- `live_state.py`：真实对局帧推送（需 env 跑在独立线程）
- `server.py`：/api/training/runs 接真实 metrics 数据

### training/（10 个）
- `sft_train.py`：真实 SFT 训练（LoRA+QLoRA，V100）
- `dpo_train.py`：DPO 偏好训练（V100）
- `pre_tokenize.py`：真实 tokenizer 加载（当前可 CPU 跑）

### video_extract/（20 个）
- `transcriber.py`：Whisper 真实 ASR（V100）
- `chart_reader.py`：VLM 真实读图（**已补完实现，注释待更新**）
- `downloader.py`：yt-dlp 真实下载（需网络+B站）
- `frame_extractor.py`：ffmpeg 真实抽帧（需视频文件）

## 二、真机校准 TODO（5 个，需模拟器/真机）

| 文件 | 行号 | 内容 |
| --- | --- | --- |
| `perception/map_parser.py` | 94 | 真机阶段：基于 coords 用颜色/模板解析地图格子 |
| `action/action_executor.py` | 67 | 真机校准：拖放部署改为"卡牌拖到格子+朝向点选" |
| `action/action_executor.py` | 81 | 真机校准：技能释放改为"点干员选中→点技能按钮" |
| `action/action_space.py` | 167 | 真机校准：等距地图按行做斜切偏移（当前正交步进占位） |
| `agent/fast_reactor.py` | 35 | 部署优先级用血狼破军强度榜数据校准（待 video_extract 产出） |

## 三、可立即做（CPU 侧，本次处理）

### ✅ 已完成
1. **chart_reader.py 过时注释更新**：文件已补完 VLM 真实实现（_load_model/read_chart 完整），但顶部 docstring 和多处注释仍写"骨架/抛 NotImplementedError"。已更新为反映真实实现状态。
2. **video_extract/README.md 状态更新**：同步 chart_reader 状态。

### 待后续
3. `perception/ocr_cost.py`：沙箱可装 PaddleOCR，验证真实 OCR 接口（非必须，V100 上装即可）

## 四、待用户决策

见 `docs/pending_decisions.md`：
1. M1 latent_bridge 接口设计（已预留 hidden_state，V100 上决定是否启用）
2. 7 个硬阻塞文件（package-lock.json + PNG）是否补推到远端

## 五、TODO 管理规范

- 新增 GPU 相关 TODO 必须标注 `# TODO-V100: <具体说明>`
- 真机相关 TODO 标注 `# TODO 真机校准: <具体说明>`
- 已完成的 TODO 必须立即删除注释，不留过时标记
- 每批开发结束时扫描一次，更新本文档
