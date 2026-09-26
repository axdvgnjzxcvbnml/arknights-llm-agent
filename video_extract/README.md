# video_extract（第十四批）

把明日方舟攻略视频（首批面向 UP 主「血狼破军」）里的两类信息提取出来转成 SFT 训练数据：

- **口播内容**（分析逻辑、结论）→ ASR 转带时间戳文本；
- **画面图表**（Excel 数据表、DPS 对比、强度榜）→ VLM 读成结构化数据。

## 流水线

```
downloader.py      yt-dlp 下载视频 + wav 音轨 + info.json（纯 CPU，需联网）
  → frame_extractor.py  ffmpeg 抽帧（interval 固定间隔 / scene 场景切换）+ manifest 时间戳
  → transcriber.py      ASR 口播转写（Whisper，# TODO-V100）
  → chart_reader.py     VLM 读图表（Qwen3-VL / UI-TARS，# TODO-V100）
  → aligner.py          口播 ↔ 画面按时间戳就近对齐（CPU 真实实现）
  → structurer.py       转 question/answer SFT 对（CPU 真实实现，带 BV+时间戳证据）
```

CPU 沙箱用各模块的 `Mock*` 实现即可跑通全链路（见 `scripts/smoke_video.py`，已并入
`bash scripts/run_smoke.sh`），不联网、不下载、不需要 GPU/真实视频。

## 配置

全部在 `video_extract/config.yaml`：UP 主 UID、下载限速/礼貌间隔、输出目录、抽帧频率、
ASR/VLM 模型名与设备、对齐容差、SFT 输出路径。

- `uploaders[0].uid`：**使用前填写血狼破军的真实 B 站 UID**，仓库不臆造。
- `asr.backend` / `vlm.backend`：默认 `mock`；V100 上分别改为 `whisper` / `qwen3vl`。

## 用法

mock 闭环（CPU）：

```bash
bash scripts/run_smoke.sh        # 第 4 段即 video_extract
python scripts/smoke_video.py    # 单独跑
```

真实抓取（在能联网、已装 `yt-dlp` 与系统 `ffmpeg` 的机器上；请自行确认合规）：

```python
from video_extract.downloader import YtDlpDownloader
dl = YtDlpDownloader()
items = dl.list_uploader_videos(uid="<血狼破军UID>", limit=5)  # 先少量
res = dl.batch_download([it["url"] for it in items])           # 限速/重试/断点续爬
```

真实转写 / 读图表在 V100：把 config 的 `asr.model`、`vlm.model` 配好后切 backend，
具体步骤并入 `docs/v100_checklist.md`（视频信息提取小节）。

## 合规与证据分级（重要）

- 视频、音频、抽帧图片是第三方受版权素材，**只写 `data/video_raw/`、`data/video_frames/`
  （均已 gitignore），绝不提交公开仓库**；仓库只含代码。
- 抓取默认开启限速、请求间隔、单次批量上限，并校验 `robots.txt`（`respect_robots: true`）。
- 证据分级（与全项目一致，见 structurer 输出的 `meta.evidence`）：
  - 画面数字 `retrieved:video_frame`、口播观点 `retrieved:video_audio`：**参考资料**，
    是 UP 主测算/主观看法，不是 PRTS/官方事实；
  - 时间戳就近关联 `inferred:timestamp`：推断，不是语义级对齐。
  - 每条 SFT 都强制带 BV 号 + 画面/口播时间戳，answer 里附第三方分析免责说明。
