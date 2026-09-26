# TODO-V100: 抽帧本身只用 ffmpeg（CPU 即可），无需 GPU；真实运行需有视频文件。
# 沙箱/冒烟用 MockFrameExtractor，不依赖真实视频，也不生成伪造图片。
"""ffmpeg 抽帧：固定间隔 / 场景切换两种模式，输出带时间戳的帧清单。

- FFmpegFrameExtractor.extract(video_path, bv_id) 调真实 ffmpeg，落地帧图 + manifest.json。
- MockFrameExtractor.extract(...) 只生成 manifest.json（placeholder=true），
  帧时间戳是确定性的占位值；下游 MockChartReader 依据时间戳产出，不读取图片字节。

import 本模块仅用标准库。
"""

import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass

from . import DEFAULT_CONFIG_PATH, load_video_config

__all__ = ["FrameRecord", "FrameExtractError", "FFmpegFrameExtractor",
           "MockFrameExtractor"]

_PTS_RE = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


class FrameExtractError(RuntimeError):
    """抽帧错误：ffmpeg/ffprobe 缺失、视频不存在、命令失败。"""


@dataclass
class FrameRecord(object):
    index: int            # 从 1 开始
    timestamp_sec: float  # 该帧在视频中的时间点
    frame_path: str       # 相对/绝对路径（mock 下文件可能不存在，见 manifest.placeholder）
    mode: str             # interval | scene

    def to_dict(self):
        return asdict(self)


class FFmpegFrameExtractor(object):
    """真实 ffmpeg 抽帧（CPU）。沙箱无视频，方法不在冒烟中调用。"""

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        cfg = config or load_video_config(config_path)
        f = cfg.get("frames", {})
        self.ffmpeg = f.get("ffmpeg_bin", "ffmpeg")
        self.ffprobe = f.get("ffprobe_bin", "ffprobe")
        self.out_root = f.get("out_root", "data/video_frames")
        self.mode = f.get("mode", "interval")
        self.interval = float(f.get("interval_sec", 5))
        self.scene_threshold = float(f.get("scene_threshold", 0.4))
        self.image_format = f.get("image_format", "jpg")

    def _ensure_ffmpeg(self):
        if shutil.which(self.ffmpeg) is None:
            raise FrameExtractError("未找到 ffmpeg（%r），无法抽帧。" % self.ffmpeg)

    def probe_duration(self, video_path):
        # type: (str) -> float
        if shutil.which(self.ffprobe) is None:
            raise FrameExtractError("未找到 ffprobe（%r），无法读取时长。" % self.ffprobe)
        if not os.path.exists(video_path):
            raise FrameExtractError("视频文件不存在: %s" % video_path)
        args = [self.ffprobe, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", video_path]
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise FrameExtractError(proc.stderr.decode("utf-8", "ignore")[-400:])
        try:
            return float(proc.stdout.decode().strip())
        except ValueError:
            return 0.0

    def extract(self, video_path, bv_id, mode=None):
        # type: (str, str, str) -> list
        self._ensure_ffmpeg()
        if not os.path.exists(video_path):
            raise FrameExtractError("视频文件不存在: %s" % video_path)
        use_mode = mode or self.mode
        out_dir = os.path.join(self.out_root, bv_id)
        os.makedirs(out_dir, exist_ok=True)
        if use_mode == "scene":
            return self._extract_scene(video_path, out_dir)
        return self._extract_interval(video_path, out_dir)

    def _extract_interval(self, video_path, out_dir):
        # fps=1/N：每 N 秒一帧；时间戳按 (index-1)*N 记录（与均匀抽帧一致）
        n = max(self.interval, 0.1)
        tmpl = os.path.join(out_dir, "frame_%05d." + self.image_format)
        args = [self.ffmpeg, "-y", "-i", video_path, "-vf", "fps=1/%s" % n, tmpl]
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise FrameExtractError(proc.stderr.decode("utf-8", "ignore")[-500:])
        records = []
        files = sorted(x for x in os.listdir(out_dir) if x.endswith("." + self.image_format))
        for i, name in enumerate(files, start=1):
            records.append(FrameRecord(
                index=i, timestamp_sec=round((i - 1) * n, 3),
                frame_path=os.path.join(out_dir, name), mode="interval"))
        self._write_manifest(out_dir, video_path, records, placeholder=False)
        return records

    def _extract_scene(self, video_path, out_dir):
        # scene 切换抽帧；用 showinfo 把 pts_time 打到 stderr，再正则取回真实时间戳
        vf = ("select='gt(scene,%s)',showinfo" % self.scene_threshold)
        tmpl = os.path.join(out_dir, "scene_%05d." + self.image_format)
        args = [self.ffmpeg, "-y", "-i", video_path, "-vf", vf,
                "-vsync", "vfr", tmpl]
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise FrameExtractError(proc.stderr.decode("utf-8", "ignore")[-500:])
        stamps = [float(m.group(1)) for m in
                  _PTS_RE.finditer(proc.stderr.decode("utf-8", "ignore"))]
        files = sorted(x for x in os.listdir(out_dir) if x.endswith("." + self.image_format))
        records = []
        for i, name in enumerate(files, start=1):
            ts = stamps[i - 1] if i - 1 < len(stamps) else 0.0
            records.append(FrameRecord(
                index=i, timestamp_sec=round(ts, 3),
                frame_path=os.path.join(out_dir, name), mode="scene"))
        self._write_manifest(out_dir, video_path, records, placeholder=False)
        return records

    def _write_manifest(self, out_dir, video_path, records, placeholder):
        manifest = {
            "video_path": video_path,
            "placeholder": placeholder,
            "count": len(records),
            "frames": [r.to_dict() for r in records],
        }
        with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)


class MockFrameExtractor(object):
    """确定性假抽帧：只写 manifest.json（placeholder=true），按固定间隔给时间戳。"""

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        cfg = config or load_video_config(config_path)
        f = cfg.get("frames", {})
        self.out_root = f.get("out_root", "data/video_frames")
        self.interval = float(f.get("interval_sec", 5))
        self.image_format = f.get("image_format", "jpg")

    def extract(self, bv_id, duration_sec=30.0, mode="interval", video_path=""):
        # type: (str, float, str, str) -> list
        out_dir = os.path.join(self.out_root, bv_id)
        os.makedirs(out_dir, exist_ok=True)
        records = []
        ts = 0.0
        i = 1
        # 含首帧（0s）；不超过时长
        while ts <= float(duration_sec) + 1e-6:
            name = "frame_%05d.%s" % (i, self.image_format)
            records.append(FrameRecord(
                index=i, timestamp_sec=round(ts, 3),
                frame_path=os.path.join(out_dir, name), mode=mode))
            ts += self.interval
            i += 1
        manifest = {
            "video_path": video_path,
            "placeholder": True,   # mock：不生成真实图片，仅时间戳占位
            "count": len(records),
            "frames": [r.to_dict() for r in records],
        }
        with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        return records
