"""实时对局状态的内存发布/订阅（LiveState）。

设计目标（dashboard_design.md §3.2）：
- ``GET /api/live/snapshot`` 从这里取**最新一帧**（HTTP 轮询降级）；
- ``WS /ws/live`` 订阅这里，每收到新帧就推给前端；
- ``ArknightsEnv`` 跑局时每步调用 ``live_state.push(frame)`` 把当前帧发布出来；
- CPU 侧没有真实 env 在跑时，``get()`` 返回一份**默认 mock 帧**（与
  ``frontend/public/mock/live.json`` 同 schema），保证前端切 USE_MOCK=false 后仍有数据。

帧结构（snake_case，与 frontend LiveFrame 类型对齐）：
    connected / episode_id / screenshot_data_url / state / vlm / decision_flow / latency_ms / ts

线程模型：FastAPI 路由与 WebSocket 都在同一 asyncio 事件循环线程内；
``push()`` 若未来从后台线程（如 env 后台跑局）调用，需用
``loop.call_soon_threadsafe`` 包一层（TODO-V100/真机阶段补）。
当前 CPU 侧 push 只从同步路由或单线程 mock 调用，无竞争问题。
"""

import asyncio
import copy
import threading
import time
from typing import Any, Dict, List, Optional

__all__ = ["LiveState", "DEFAULT_MOCK_FRAME"]


def _ts_iso() -> str:
    import datetime
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 默认 mock 帧（与 frontend/public/mock/live.json 同结构，snake_case）
# 无真实 env 跑局时，/api/live/snapshot 与 /ws/live 都返回这份。
# ---------------------------------------------------------------------------
DEFAULT_MOCK_FRAME: Dict[str, Any] = {
    "connected": True,
    "episode_id": "EP-MOCK-0001",
    "screenshot_data_url": None,
    "state": {
        "cost": 15,
        "available_operators": [
            {"name": "先锋", "profession": "先锋", "cost": 2},
            {"name": "狙击", "profession": "狙击", "cost": 3},
            {"name": "医疗", "profession": "医疗", "cost": 3},
        ],
        "skill_cooldowns": [
            {"operator": "能天使", "ready": False, "remaining_ms": 8000},
            {"operator": "塞雷娅", "ready": True, "remaining_ms": 0},
        ],
        "enemies": [
            {"name": "重装敌人", "count": 3, "status": "estimated"},
            {"name": "士兵", "count": 5, "status": "cv"},
        ],
        "deployable_grids": ["A1", "A2", "A3", "A4", "A5",
                              "B1", "B2", "B3", "B4", "B5"],
    },
    "vlm": {
        "situation": "当前费用15，左侧有3个重装敌人接近，前排阻挡压力上升，局面偏防守。",
        "strategic_advice": "建议优先补术师应对重装，费用足够时部署医疗稳住血线。",
        "confidence": 0.72,
        "evidence": [
            {"level": "vlm", "source": "MockVLMAnalyzer"},
            {"level": "retrieved", "source": "PRTS攻略：重装敌人弱法术"},
        ],
    },
    "decision_flow": [
        {
            "step": 1,
            "reasoning": "开局费用紧张，先下先锋产费，建立阻挡与回费。",
            "action": "deploy(operator=先锋, grid=A3, direction=right)",
            "confidence": 0.90,
            "knowledge_used": [
                {"level": "retrieved", "source": "PRTS 3-8 攻略", "snippet": "先锋起手回费"},
            ],
            "latency_ms": 1180,
        },
        {
            "step": 2,
            "reasoning": "重装敌人法抗低、物抗高，需术师输出；SpawnTracker 显示其为估算，已等待 CV 确认。",
            "action": "deploy(operator=术师, grid=B2, direction=down)",
            "confidence": 0.78,
            "knowledge_used": [
                {"level": "retrieved", "source": "PRTS 敌人表：重装敌人"},
                {"level": "estimated", "source": "SpawnTracker 均匀时间轴"},
            ],
            "latency_ms": 1402,
        },
        {
            "step": 3,
            "reasoning": "前排血线承压，部署医疗抬血并等待能天使技能。",
            "action": "deploy(operator=医疗, grid=B4, direction=left)",
            "confidence": 0.82,
            "knowledge_used": [
                {"level": "inferred", "source": "占位规则：血线承压→补医疗"},
            ],
            "latency_ms": 1265,
        },
    ],
    "latency_ms": {"capture": 18, "cv": 36, "retrieval": 58,
                    "llm": 1265, "action": 205, "total": 1582},
    "ts": "2026-09-26T10:00:05+08:00",
}


class LiveState(object):
    """实时对局帧的内存存储 + 发布订阅。

    - ``push(frame)``：env 跑局时调用，更新最新帧并通知所有 WS 订阅者；
    - ``get()``：HTTP snapshot 接口取最新帧（无帧时返回默认 mock 帧）；
    - ``subscribe()`` / ``unsubscribe()``：WS 连接管理。

    线程安全模型（重要）：
        ``ArknightsEnv.run_episode()`` 是**同步**方法，未来接入 push() 时几乎
        一定跑在 uvicorn 事件循环**之外**的线程（线程池 / 独立线程）。而
        ``asyncio.Queue.put_nowait()`` **不是线程安全的**——从非事件循环线程
        调用可能不唤醒 get 等待者，导致 WS 端收不到帧。

        修复方式：``subscribe()`` 时保存创建队列的事件循环引用；``push()`` 时
        检测当前线程是否是该 loop 的线程：
        - 是 → 直接 ``put_nowait``（零开销，同线程内安全）；
        - 否 → ``loop.call_soon_threadsafe(_put, q, frame)``（安全跨线程调度）。

        ``_latest`` / ``_subscribers`` / ``_push_count`` 的访问由
        ``threading.Lock`` 保护，与事件循环无关。
    """

    def __init__(self, default_frame: Optional[Dict[str, Any]] = None) -> None:
        self._lock = threading.Lock()
        self._latest: Dict[str, Any] = copy.deepcopy(default_frame or DEFAULT_MOCK_FRAME)
        # 每个订阅者 = (queue, 创建时的事件循环)；subscribe 一定在事件循环线程调用
        self._subscribers: List = []
        self._push_count = 0

    # ---------------- 发布 ----------------
    @staticmethod
    def _put_to_queue(q: asyncio.Queue, frame: Dict[str, Any]) -> None:
        """在事件循环线程内执行的 put：满则丢最旧一帧再放（保最新）。"""
        try:
            q.put_nowait(frame)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
                q.put_nowait(frame)
            except Exception:
                pass

    def push(self, frame: Dict[str, Any]) -> None:
        """发布一帧。覆盖最新帧，并通知所有 WS 订阅者。

        跨线程安全：若调用线程不是订阅者 loop 的线程，用
        ``loop.call_soon_threadsafe`` 调度 put 到事件循环线程执行。
        """
        with self._lock:
            self._latest = copy.deepcopy(frame)
            self._push_count += 1
            subscribers = list(self._subscribers)  # 拷贝，避免持锁时做 call_soon

        for q, loop in subscribers:
            try:
                running = asyncio.get_running_loop()
                if running is loop:
                    # 同事件循环线程，直接 put（零开销）
                    self._put_to_queue(q, frame)
                    continue
            except RuntimeError:
                # 当前线程没有运行中的事件循环（纯同步线程），走 call_soon_threadsafe
                pass
            # 跨线程：调度到订阅者的事件循环线程执行
            loop.call_soon_threadsafe(self._put_to_queue, q, frame)

    # ---------------- 读取 ----------------
    def get(self) -> Dict[str, Any]:
        """取最新帧的深拷贝（调用方修改不影响内部状态）。"""
        with self._lock:
            return copy.deepcopy(self._latest)

    @property
    def push_count(self) -> int:
        return self._push_count

    # ---------------- 订阅 ----------------
    def subscribe(self) -> asyncio.Queue:
        """新建一个订阅队列并注册。调用方负责在断开时 unsubscribe。

        必须在事件循环线程内调用（WebSocket 路由天然满足），以便保存 loop 引用
        供跨线程 push 时 ``call_soon_threadsafe`` 使用。
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=16)
        loop = asyncio.get_running_loop()
        with self._lock:
            self._subscribers.append((q, loop))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers[:] = [item for item in self._subscribers if item[0] is not q]

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)
