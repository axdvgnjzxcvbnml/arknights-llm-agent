"""api.live_state.LiveState 单元测试。

重点验证跨线程 push 的线程安全性：ArknightsEnv.run_episode() 是同步方法，
未来接入 push() 时跑在 uvicorn 事件循环之外的线程；asyncio.Queue.put_nowait
不是线程安全的，LiveState 必须用 loop.call_soon_threadsafe 跨线程调度。
"""

import asyncio
import threading
import time

import pytest

from api.live_state import DEFAULT_MOCK_FRAME, LiveState


# ---------------------------------------------------------------------------
# 基础：默认帧 / push 更新 latest / subscriber_count
# ---------------------------------------------------------------------------

def test_get_returns_default_frame():
    state = LiveState()
    frame = state.get()
    assert frame["connected"] is True
    assert frame["state"]["cost"] == 15
    assert frame["episode_id"] == "EP-MOCK-0001"
    # get 返回浅拷贝，修改不影响内部
    frame["state"]["cost"] = 999
    assert state.get()["state"]["cost"] == 15


def test_custom_default_frame():
    custom = {"connected": False, "state": {"cost": 0}}
    state = LiveState(default_frame=custom)
    assert state.get()["connected"] is False


def test_push_updates_latest_and_count():
    state = LiveState()
    assert state.push_count == 0
    state.push({"connected": True, "state": {"cost": 25}})
    assert state.push_count == 1
    assert state.get()["state"]["cost"] == 25
    state.push({"connected": True, "state": {"cost": 30}})
    assert state.push_count == 2
    assert state.get()["state"]["cost"] == 30


# ---------------------------------------------------------------------------
# 同线程 push：在事件循环线程里 subscribe + push，验证通知
# ---------------------------------------------------------------------------

def test_same_thread_push_notifies_subscriber():
    state = LiveState()
    received = []

    async def scenario():
        q = state.subscribe()
        assert state.subscriber_count == 1
        # 同线程 push（在事件循环协程里调用）
        state.push({"step": 1, "cost": 10})
        frame = await asyncio.wait_for(q.get(), timeout=1.0)
        received.append(frame)

    asyncio.run(scenario())
    assert len(received) == 1
    assert received[0]["step"] == 1
    assert received[0]["cost"] == 10


def test_unsubscribe_stops_notifications():
    state = LiveState()

    async def scenario():
        q = state.subscribe()
        assert state.subscriber_count == 1
        state.unsubscribe(q)
        assert state.subscriber_count == 0
        # push 后队列不应收到帧（已注销）
        state.push({"step": 99})
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(q.get(), timeout=0.3)

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# 跨线程 push（核心测试）：事件循环在一个线程，push 在另一个线程
# 模拟 uvicorn 主线程跑 WS + env 跑局线程调 push()
# ---------------------------------------------------------------------------

def test_cross_thread_push_notifies_subscriber():
    state = LiveState()
    received = []
    loop_ready = threading.Event()

    def run_loop():
        """在独立线程里跑事件循环（模拟 uvicorn 主线程）。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def wait_for_frame():
            q = state.subscribe()  # 协程内有 running loop
            loop_ready.set()
            frame = await asyncio.wait_for(q.get(), timeout=3.0)
            received.append(frame)

        try:
            loop.run_until_complete(wait_for_frame())
        finally:
            loop.close()

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()
    # 等事件循环启动并完成 subscribe
    assert loop_ready.wait(timeout=2.0), "事件循环线程未在超时内就绪"
    time.sleep(0.05)  # 给 q.get() 进入等待的时间

    # 从主线程（模拟 env 跑局线程）跨线程 push
    test_frame = {"connected": True, "state": {"cost": 42}, "step": "cross-thread"}
    state.push(test_frame)

    t.join(timeout=4.0)
    assert not t.is_alive(), "事件循环线程未在超时内结束（可能丢帧了）"
    assert len(received) == 1, "跨线程 push 后订阅者未收到帧"
    assert received[0]["state"]["cost"] == 42
    assert received[0]["step"] == "cross-thread"
    # get() 跨线程读也应返回最新帧
    assert state.get()["state"]["cost"] == 42


def test_cross_thread_multiple_frames_in_order():
    """跨线程连续 push 多帧，验证订阅者按序收到（不丢不重）。"""
    state = LiveState()
    received = []
    loop_ready = threading.Event()
    n_frames = 5

    def run_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def consume():
            q = state.subscribe()
            loop_ready.set()
            for _ in range(n_frames):
                frame = await asyncio.wait_for(q.get(), timeout=3.0)
                received.append(frame["seq"])

        try:
            loop.run_until_complete(consume())
        finally:
            loop.close()

    t = threading.Thread(target=run_loop, daemon=True)
    t.start()
    assert loop_ready.wait(timeout=2.0)
    time.sleep(0.05)

    # 跨线程连续 push
    for i in range(n_frames):
        state.push({"seq": i, "state": {"cost": i}})
        time.sleep(0.02)

    t.join(timeout=4.0)
    assert not t.is_alive()
    assert received == list(range(n_frames)), f"帧顺序/数量不对: {received}"


# ---------------------------------------------------------------------------
# subscribe 必须在事件循环线程内调用（保存 loop 引用）
# ---------------------------------------------------------------------------

def test_subscribe_outside_loop_raises():
    """在没有运行中事件循环的线程里调用 subscribe()，应抛 RuntimeError。"""
    state = LiveState()
    with pytest.raises(RuntimeError):
        state.subscribe()


def test_multiple_subscribers_cross_thread():
    """多个订阅者（不同 loop），跨线程 push 应同时通知所有订阅者。"""
    state = LiveState()
    results = {"t1": [], "t2": []}
    ready1 = threading.Event()
    ready2 = threading.Event()

    def make_consumer(name, ready):
        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def consume():
                q = state.subscribe()
                ready.set()
                frame = await asyncio.wait_for(q.get(), timeout=3.0)
                results[name].append(frame["tag"])

            try:
                loop.run_until_complete(consume())
            finally:
                loop.close()
        return run

    t1 = threading.Thread(target=make_consumer("t1", ready1), daemon=True)
    t2 = threading.Thread(target=make_consumer("t2", ready2), daemon=True)
    t1.start()
    t2.start()
    assert ready1.wait(timeout=2.0)
    assert ready2.wait(timeout=2.0)
    time.sleep(0.05)
    assert state.subscriber_count == 2

    state.push({"tag": "broadcast", "state": {"cost": 7}})

    t1.join(timeout=4.0)
    t2.join(timeout=4.0)
    assert not t1.is_alive() and not t2.is_alive()
    assert results["t1"] == ["broadcast"]
    assert results["t2"] == ["broadcast"]
