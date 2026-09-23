# ADB 轻量封装（自实现，不依赖 maa-framework，保持项目 MIT）。
# 参考 MaaAssistantArknights 的 ADB 控制层接口思路，但命令与解析全部自己写；
# 未拷贝其代码/资源，也未使用其 AGPL 绑定。坐标由使用者参考 MAA 后写入本地 config。
"""ADB 控制器：连接 / 点击 / 滑动 / 截屏 / 按键，面向 MuMu 模拟器。

设计：
- ADBController 走 adb 原语（connect / devices / input tap / input swipe /
  exec-out screencap / input keyevent），覆盖自动战斗所需的绝大多数操作。
- 连接（无 adb / 连不上 / 设备离线）直接抛 ADBControllerError——没连上就无法继续；
  单条操作（tap/swipe/key/screencap）失败/超时不静默，统一返回 OpResult（含
  ok/failed/timeout/offline 与 error 文案、耗时），由上层决定是否继续后续动作。
- MockADBController 不执行任何真实命令，只把操作写入日志，供 CPU 闭环验证。
"""

import shutil
import subprocess
import time
from typing import List, Optional

from pydantic import BaseModel, Field

from .config import DEFAULT_CONFIG_PATH, load_action_config

__all__ = ["ADBControllerError", "OpResult", "ADBController", "MockADBController"]


class ADBControllerError(RuntimeError):
    """连接级致命错误（未找到 adb / 无法 connect / 设备不在线）。"""


class OpResult(BaseModel):
    op: str
    success: bool = False
    status: str = "ok"              # ok / failed / timeout / offline
    error: str = ""
    duration_ms: float = 0.0
    detail: dict = Field(default_factory=dict)


class _BaseController(object):
    def online(self):
        # type: () -> bool
        raise NotImplementedError

    def tap(self, x, y):
        # type: (int, int) -> OpResult
        raise NotImplementedError

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        # type: (int, int, int, int, int) -> OpResult
        raise NotImplementedError

    def key(self, keycode):
        # type: (int) -> OpResult
        raise NotImplementedError

    def screencap_png(self):
        # type: () -> bytes
        raise NotImplementedError


class ADBController(_BaseController):
    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        cfg = config or load_action_config(config_path)
        adb = cfg.get("device_adb", {})
        self.adb_path = adb.get("adb_path", "adb")
        self.host = adb.get("host", "127.0.0.1")
        self.port = int(adb.get("port", 7555))
        self.serial = adb.get("serial") or "%s:%d" % (self.host, self.port)
        self.connect_on_start = bool(cfg.get("adb", {}).get(
            "connect_on_start", adb.get("connect_on_start", True)))
        self.timeout = float(cfg.get("adb", {}).get("command_timeout_sec", 10))
        self._online = False

    # ---------- 连接 ----------
    def _base_cmd(self):
        return [self.adb_path, "-s", self.serial]

    def is_available(self):
        return shutil.which(self.adb_path) is not None

    def connect(self):
        if not self.is_available():
            raise ADBControllerError(
                "未找到 adb（%s）。请安装 platform-tools 或在配置中指定 adb_path。"
                % self.adb_path)
        if self.connect_on_start:
            try:
                subprocess.run([self.adb_path, "connect", self.serial],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=self.timeout)
            except (OSError, subprocess.SubprocessError) as exc:
                raise ADBControllerError("adb connect %s 失败：%s" % (self.serial, exc))
        if not self._query_online():
            raise ADBControllerError(
                "设备 %s 不在线：请确认 MuMu 已启动并 adb connect（默认 127.0.0.1:7555，"
                "新版 MuMu 端口可能为 16384/16416）。" % self.serial)
        self._online = True

    def _query_online(self):
        try:
            out = subprocess.run([self.adb_path, "devices"], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, timeout=self.timeout
                                 ).stdout.decode("utf-8", "ignore")
        except (OSError, subprocess.SubprocessError):
            return False
        return any(line.startswith(self.serial + "\t") and "\tdevice" in line
                   for line in out.splitlines())

    def online(self):
        self._online = self._query_online()
        return self._online

    def _ensure_connected(self):
        if not self._online and not self.online():
            raise ADBControllerError("设备 %s 已离线，操作中止。" % self.serial)

    # ---------- 命令执行 ----------
    def _run_shell(self, op, shell_args):
        # type: (str, List[str]) -> OpResult
        try:
            self._ensure_connected()
        except ADBControllerError as exc:
            return OpResult(op=op, success=False, status="offline", error=str(exc))
        start = time.time()
        try:
            proc = subprocess.run(self._base_cmd() + ["shell"] + shell_args,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return OpResult(op=op, success=False, status="timeout",
                            error="命令超时(>%.0fs): %s" % (self.timeout, shell_args),
                            duration_ms=(time.time() - start) * 1000.0)
        except (OSError, subprocess.SubprocessError) as exc:
            return OpResult(op=op, success=False, status="failed", error=str(exc),
                            duration_ms=(time.time() - start) * 1000.0)
        dur = (time.time() - start) * 1000.0
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", "ignore").strip() or "非零退出码"
            return OpResult(op=op, success=False, status="failed",
                            error="%s（%s）" % (err, shell_args), duration_ms=dur)
        return OpResult(op=op, success=True, status="ok", duration_ms=dur,
                        detail={"args": shell_args})

    # ---------- 操作原语 ----------
    def tap(self, x, y):
        x, y = int(round(x)), int(round(y))
        return self._run_shell("tap", ["input", "tap", str(x), str(y)])

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        x1, y1, x2, y2 = (int(round(v)) for v in (x1, y1, x2, y2))
        return self._run_shell("swipe", [
            "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(int(duration_ms))])

    def key(self, keycode):
        return self._run_shell("key", ["input", "keyevent", str(int(keycode))])

    def screencap_png(self):
        # type: () -> bytes
        try:
            self._ensure_connected()
        except ADBControllerError as exc:
            raise ADBControllerError(str(exc))
        try:
            proc = subprocess.run(
                self._base_cmd() + ["exec-out", "screencap", "-p"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise ADBControllerError("截屏超时（>%.0fs）" % self.timeout)
        if proc.returncode != 0 or not proc.stdout:
            raise ADBControllerError("截屏失败：%s" %
                                     proc.stderr.decode("utf-8", "ignore").strip())
        return proc.stdout

    def press_back(self):
        return self.key(4)        # KEYCODE_BACK


class MockADBController(_BaseController):
    """记录所有操作到日志，不执行真实 adb；默认恒在线。"""

    def __init__(self, online_state=True):
        self._online = bool(online_state)
        self.log = []  # type: List[OpResult]

    def connect(self):
        self._online = True

    def online(self):
        return self._online

    def set_online(self, value):
        self._online = bool(value)

    def reset_log(self):
        self.log = []

    def _record(self, op, status="ok", **detail):
        r = OpResult(op=op, success=(status == "ok"), status=status, detail=detail)
        self.log.append(r)
        return r

    def tap(self, x, y):
        if not self._online:
            return self._record("tap", "offline", error="设备离线", x=int(x), y=int(y))
        return self._record("tap", x=int(round(x)), y=int(round(y)))

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        if not self._online:
            return self._record("swipe", "offline", error="设备离线")
        return self._record("swipe", x1=int(round(x1)), y1=int(round(y1)),
                            x2=int(round(x2)), y2=int(round(y2)),
                            duration_ms=int(duration_ms))

    def key(self, keycode):
        if not self._online:
            return self._record("key", "offline", error="设备离线")
        return self._record("key", keycode=int(keycode))

    def screencap_png(self):
        if not self._online:
            raise ADBControllerError("设备离线，无法截屏")
        self._record("screencap")
        return b""  # mock 不产生真实图像（也不入库任何游戏素材）

    def press_back(self):
        return self.key(4)

    def ops(self):
        # type: () -> List[str]
        return [r.op for r in self.log]
