# TODO-V100: 本模块不依赖 GPU；真实截屏依赖 MuMu 模拟器与 adb（CPU/真机侧）。
# 无模拟器环境统一用 MockScreenCapture（程序生成合成帧，不含任何真实游戏素材）。
"""屏幕截屏：ADB（MuMu 模拟器）真实实现 + Mock 合成帧。

- ADBScreenCapture：走 `adb exec-out screencap -p`（或 pull）取 PNG 并解码，需要真机/模拟器。
- MockScreenCapture：用 numpy 生成确定性合成 BGR 帧，供 CPU 冒烟测试；可选择从
  data/mock/frames 读取自制 PNG（仍不得放入真实游戏截图）。

import 本模块不会拉起 cv2/torch 等重依赖：cv2 仅在真实解码/读取 PNG 时延迟导入。
"""

import os
import shutil
import subprocess
import time

import numpy as np

from .config import DEFAULT_CONFIG_PATH, load_perception_config

__all__ = ["ScreenCaptureError", "ScreenCapture", "ADBScreenCapture",
           "MockScreenCapture", "get_screen_capture"]


class ScreenCaptureError(RuntimeError):
    """截屏链路错误（无 adb / 未连接 / 模拟器未就绪 / 解码失败）。"""


class ScreenCapture(object):
    """截屏接口基类：capture() 返回 BGR uint8 的 numpy 数组 (H, W, 3)。"""

    def connect(self):
        raise NotImplementedError

    def capture(self):
        # type: () -> np.ndarray
        raise NotImplementedError

    def close(self):
        pass

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def _decode_png(png_bytes):
    # type: (bytes) -> np.ndarray
    import cv2  # 延迟导入：避免 import 本模块就要求 opencv

    buf = np.frombuffer(png_bytes, dtype=np.uint8)
    frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if frame is None:
        raise ScreenCaptureError("截屏 PNG 解码失败（数据为空或不是有效图像）")
    return frame


class ADBScreenCapture(ScreenCapture):
    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        cfg = config or load_perception_config(config_path)
        adb = cfg["adb"]
        cap = cfg["capture"]
        self.adb_path = adb.get("adb_path", "adb")
        self.host = adb["host"]
        self.port = int(adb["port"])
        self.serial = adb.get("serial") or "%s:%d" % (self.host, self.port)
        self.method = adb.get("screencap_method", "exec-out")
        self.connect_on_start = bool(adb.get("connect_on_start", True))
        self.expected_size = (int(cap["width"]), int(cap["height"]))
        self._connected = False

    # ---- 基础命令 ----
    def _adb_base(self):
        return [self.adb_path, "-s", self.serial]

    def is_available(self):
        # type: () -> bool
        """adb 可执行文件是否存在（不代表模拟器已连接）。"""
        return shutil.which(self.adb_path) is not None

    def connect(self):
        if not self.is_available():
            raise ScreenCaptureError(
                "未找到 adb（%s）。请安装 platform-tools 或在 configs/perception.yaml "
                "配置 adb_path。" % self.adb_path)
        if self.connect_on_start:
            try:
                subprocess.run([self.adb_path, "connect", self.serial],
                               check=False, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=10)
            except (OSError, subprocess.SubprocessError) as exc:
                raise ScreenCaptureError("adb connect %s 失败：%s" % (self.serial, exc))
        # 确认设备在线
        try:
            out = subprocess.run([self.adb_path, "devices"], check=False,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 timeout=10).stdout.decode("utf-8", "ignore")
        except (OSError, subprocess.SubprocessError) as exc:
            raise ScreenCaptureError("adb devices 查询失败：%s" % exc)
        online = any(line.startswith(self.serial + "\t") and
                     ("device" in line) for line in out.splitlines())
        if not online:
            raise ScreenCaptureError(
                "设备 %s 不在线。请确认 MuMu 已启动并 adb connect（默认 127.0.0.1:7555，"
                "新版 MuMu 端口可能为 16384/16416）。adb devices 输出：\n%s"
                % (self.serial, out.strip()))
        self._connected = True

    def capture(self):
        if not self._connected:
            self.connect()
        try:
            if self.method == "pull":
                return self._capture_pull()
            return self._capture_exec_out()
        except ScreenCaptureError:
            raise
        except (OSError, subprocess.SubprocessError) as exc:
            raise ScreenCaptureError("adb 截屏失败：%s" % exc)

    def _capture_exec_out(self):
        proc = subprocess.run(self._adb_base() + ["exec-out", "screencap", "-p"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        if proc.returncode != 0 or not proc.stdout:
            raise ScreenCaptureError(
                "exec-out screencap 失败：%s"
                % proc.stderr.decode("utf-8", "ignore").strip())
        return _decode_png(proc.stdout)

    def _capture_pull(self):
        remote = "/sdcard/ak_agent_screen.png"
        local = os.path.join(os.path.expanduser("~"), ".ak_agent_screen.png")
        subprocess.run(self._adb_base() + ["shell", "screencap", "-p", remote],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=15)
        try:
            subprocess.run(self._adb_base() + ["pull", remote, local], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
            with open(local, "rb") as f:
                return _decode_png(f.read())
        finally:
            subprocess.run(self._adb_base() + ["shell", "rm", "-f", remote],
                           check=False, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)


class MockScreenCapture(ScreenCapture):
    """生成确定性合成帧；同一 seed + 帧序号产出同一画面，便于测试与回放。"""

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH, frame_index=0):
        cfg = config or load_perception_config(config_path)
        cap = cfg["capture"]
        mock = cap.get("mock", {})
        self.width = int(cap["width"])
        self.height = int(cap["height"])
        self.channels = int(cap.get("channels", 3))
        self.seed = int(mock.get("seed", 7))
        self.fixture_dir = mock.get("fixture_dir", "")
        self.frame_index = int(frame_index)
        self._fixtures = self._list_fixtures()

    def _list_fixtures(self):
        if self.fixture_dir and os.path.isdir(self.fixture_dir):
            return sorted(os.path.join(self.fixture_dir, f)
                          for f in os.listdir(self.fixture_dir)
                          if f.lower().endswith(".png"))
        return []

    def connect(self):
        return True

    def _synthetic(self, idx):
        # 确定性合成：横向渐变 + 两个色块 + 网格线，仅用于打通接口，不模拟真实 UI
        rng = np.random.default_rng(self.seed + idx)
        h, w = self.height, self.width
        xs = np.linspace(0, 255, w, dtype=np.uint8)
        frame = np.repeat(xs[np.newaxis, :], h, axis=0)
        frame = np.stack([frame,
                          np.full((h, w), 40, dtype=np.uint8),
                          (255 - frame)], axis=2)
        # 两个"物体"色块
        for _ in range(2):
            x0 = int(rng.integers(0, w - 80)); y0 = int(rng.integers(0, h - 80))
            frame[y0:y0 + 60, x0:x0 + 60] = rng.integers(0, 255, 3, dtype=np.uint8)
        return np.ascontiguousarray(frame)

    def capture(self):
        idx = self.frame_index
        self.frame_index += 1
        if self._fixtures:
            import cv2  # 延迟导入
            path = self._fixtures[idx % len(self._fixtures)]
            frame = cv2.imread(path, cv2.IMREAD_COLOR)
            if frame is not None:
                return frame
        return self._synthetic(idx)

    def capture_with_meta(self):
        # type: () -> tuple
        frame = self.capture()
        from .schemas import FrameMeta
        meta = FrameMeta(width=frame.shape[1], height=frame.shape[0],
                         channels=frame.shape[2] if frame.ndim == 3 else 1,
                         source="mock", timestamp=time.time())
        return frame, meta


def get_screen_capture(backend="mock", config=None, config_path=DEFAULT_CONFIG_PATH):
    # type: (str, dict, str) -> ScreenCapture
    """工厂：backend 取 "mock"（默认）或 "adb"。默认不连真机，保证 CI 安全。"""
    if backend == "mock":
        return MockScreenCapture(config=config, config_path=config_path)
    if backend == "adb":
        return ADBScreenCapture(config=config, config_path=config_path)
    raise ValueError("未知截屏后端：%r（可选 mock/adb）" % backend)
