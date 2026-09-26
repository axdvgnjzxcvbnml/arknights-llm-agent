"""video_extract：从攻略视频提取"口播 + 画面图表"两类信息并转成 SFT 数据。

流水线（见 scripts/smoke_video.py 的 mock 串联）：
    downloader   yt-dlp 下载视频/音频（纯 CPU，真实需联网，沙箱用 mock）
      -> frame_extractor  ffmpeg 抽帧（固定间隔 / 场景切换）
      -> transcriber     ASR 口播转写（骨架，# TODO-V100，CPU 用 mock）
      -> chart_reader    VLM 读图表（骨架，# TODO-V100，CPU 用 mock）
      -> aligner         口播↔画面时间轴就近对齐（CPU 真实实现）
      -> structurer      转 question/answer SFT 对（CPU 真实实现，带 BV+时间戳证据）

设计约束：
- import video_extract 只用标准库 + pyyaml，**不拉起** torch/transformers/numpy/whisper；
  yt-dlp/ffmpeg/ASR/VLM 全部在方法内部延迟调用，真实抓取/推理不在 import 期发生。
- 视频/音频/抽帧属受版权保护的第三方素材，只写 data/（gitignore），绝不入库。
- 证据分级与全项目一致：图表数字/口播原文=retrieved（参考资料，非 PRTS 事实），
  时间轴就近关联=inferred，并强制标注来源 BV 号 + 时间戳。
"""

import os

import yaml

__all__ = [
    "DEFAULT_CONFIG_PATH",
    "load_video_config",
    "REQUIRED_SECTIONS",
]

DEFAULT_CONFIG_PATH = os.path.join("video_extract", "config.yaml")

# 配置必须包含的顶层段（缺段直接报错，不静默用默认值掩盖配置错误）
REQUIRED_SECTIONS = (
    "uploaders", "categorize", "download", "frames", "asr", "vlm", "align", "structure",
)


def load_video_config(path=DEFAULT_CONFIG_PATH):
    # type: (str) -> dict
    """读取 video_extract/config.yaml；文件缺失或缺段时给明确报错。"""
    if not os.path.exists(path):
        raise FileNotFoundError("视频提取配置文件不存在: %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    missing = [s for s in REQUIRED_SECTIONS if s not in cfg]
    if missing:
        raise ValueError("配置文件 %s 缺少段: %s" % (path, ", ".join(missing)))
    return cfg
