#!/usr/bin/env python3
"""把 mock 对局导出成「对局回放界面」用的结构化 JSON。

为什么需要这个脚本
------------------
`results/episode_report_win.txt` 与 `results/agent_decision_log.txt` 都是**渲染后的纯文本**，
前端没法直接消费；而 `results/` 又被 .gitignore 排除，clone 下来是空的。
本脚本复用仓库现有的 mock 组件（`env.mock_env.build_mock_env` + `agent` 的
slow/bridge/fast/knowledge），跑完整一局并把**结构化对象**（GameState / AgentDecision /
KnowledgeBundle / PlanResult / RewardBreakdown / Reflection）落成 JSON，作为 `web/` 的静态
mock 数据。数据 100% 来自仓库真实代码路径，不是手写编的。

导出的两局与冒烟脚本一致：
- win  ：10 步通关，总分 +100（对应 results/episode_report_win.txt）
- lose ：3 步目标耐久归零，漏怪 3 点，总分 -30（对应 results/episode_report_lose.txt）

同时把两份原始文本日志（对局报告 + 决策日志）一并导出，供前端「原始日志」抽屉对照查看。

用法（仓库根目录）::

    python3 web/scripts/export_mock.py            # 导出到 web/src/mock/
    python3 web/scripts/export_mock.py --out /tmp/mock

依赖：仓库本身的最小冒烟依赖（numpy / pydantic / pyyaml），无需 GPU、模拟器与 PRTS 数据。
"""

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

DEFAULT_OUT = os.path.join(ROOT, "web", "src", "mock")

# 与 scripts/smoke_env.py 保持一致的两局脚本化结局
EPISODES = [
    {"id": "ep-3-8-win", "mode": "win", "stage_id": "3-8", "win_in": 10, "lose_in": 3,
     "title": "3-8 通关局（10 步）", "source": "env.run_episode + agent mock 全链路"},
    {"id": "ep-3-8-lose", "mode": "lose", "stage_id": "3-8", "win_in": 10, "lose_in": 3,
     "title": "3-8 失败局（3 步漏怪）", "source": "env.run_episode + agent mock 全链路"},
]

OUTCOME_CN = {"win": "通关", "defeat": "失败（生命归零）",
              "timeout": "到达步数上限", "aborted": "中止"}


# ------------------------------------------------------------------ 工具函数
def _ms(t0):
    """perf_counter 起点 -> 毫秒（保留 3 位，mock 链路耗时很小，1 位会全成 0.0）。"""
    return round((time.perf_counter() - t0) * 1000.0, 3)


def camelize(obj):
    """递归把 snake_case 键转成 camelCase，让前端直接用 JS 习惯字段名。"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            parts = str(k).split("_")
            out[parts[0] + "".join(p.title() for p in parts[1:])] = camelize(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [camelize(v) for v in obj]
    return obj


def dump(model):
    """pydantic v2 / v1 双兼容地导出为可 JSON 序列化的 dict。"""
    if model is None:
        return None
    if hasattr(model, "model_dump"):
        return camelize(model.model_dump(mode="json"))
    return camelize(json.loads(model.json()))


# ------------------------------------------------------------------ 单局采集
def capture_episode(spec):
    """跑完整一局，返回前端契约格式的 {episode, steps} 文档。

    循环体与 `ArknightsEnv.run_episode()` 完全一致（knowledge -> slow -> bridge -> fast
    -> env.step），只是额外把每步**决策前的结构化状态**与 Agent 各阶段产物一并留存。
    """
    from env.mock_env import build_mock_env

    env = build_mock_env(mode=spec["mode"], stage_id=spec["stage_id"],
                         win_in=spec["win_in"], lose_in=spec["lose_in"])
    env.reset(spec["stage_id"])

    steps = []
    map_topology = None
    done = False
    while not done and env.tick < env.max_steps:
        # 决策前状态：env 内部 perceive 的结果（不能再调一次 perceive，
        # 否则 ScriptedPerception 的计数会提前触发通关/失败终局信号）
        pf = env._pf
        state_before = pf.state

        lat = {}

        t = time.perf_counter()
        knowledge = env.knowledge.gather(state_before)
        lat["knowledge_ms"] = _ms(t)

        t = time.perf_counter()
        decision = env.slow.think(
            stage_id=env.stage_id, elapsed_sec=env.elapsed_sec,
            state_text=pf.state_text, knowledge=knowledge, state=state_before)
        lat["slow_ms"] = _ms(t)

        t = time.perf_counter()
        bridge = env.bridge.project(decision)
        lat["bridge_ms"] = _ms(t)

        t = time.perf_counter()
        command = env.fast.react(state_before, decision, bridge)
        lat["fast_ms"] = _ms(t)

        t = time.perf_counter()
        _next_state, step_reward, done, info = env.step(command, decision=decision,
                                                        knowledge=knowledge)
        lat["step_ms"] = _ms(t)

        record = env.steps[-1]                     # EnvStep：含执行结果与奖励
        lat.update({k: round(float(v), 3) for k, v in record.latency_ms.items()})
        lat = camelize(lat)

        reflection = env.slow.reflect(decision, record.plan_result, pf.state_text)

        if map_topology is None and state_before.game_map is not None:
            gm = state_before.game_map
            map_topology = {"cols": gm.cols, "rows": gm.rows,
                            "cells": [{"cellId": c.cell_id, "col": c.col, "row": c.row,
                                       "terrain": c.terrain, "deployable": c.deployable}
                                      for c in gm.cells]}

        steps.append(build_step_dto(record, pf, state_before, knowledge, decision,
                                    bridge, command, reflection, lat, step_reward))

    log = env.get_log()
    episode = build_episode_dto(spec, log, steps, env, map_topology)
    return {"schemaVersion": 1, "episode": episode, "steps": steps}


def build_step_dto(record, pf, state_before, knowledge, decision, bridge, command,
                   reflection, lat, step_reward):
    """一步的完整可解释记录（前端时间轴的一个节点）。"""
    vlm = pf.analysis
    return {
        "step": record.step,
        "elapsedSec": record.elapsed_sec,
        # ---- 决策前的游戏状态（LLM 实际看到的画面解析结果）----
        "state": {
            "stageId": state_before.stage_id,
            "timestamp": state_before.timestamp,
            "timingSource": state_before.timing_source,
            "cost": dump(state_before.cost),
            "lifePoints": state_before.life_points,
            "deployUsed": state_before.deploy_used,
            "deployLimit": state_before.deploy_limit,
            "operatorCards": [dump(c) for c in state_before.operator_cards],
            "deployed": [dump(d) for d in state_before.deployed],
            "skills": [dump(s) for s in state_before.skills],
            "enemiesOnField": [dump(e) for e in state_before.enemies_on_field],
            "spawnPlan": [dump(s) for s in state_before.spawn_plan],
            # 地图拓扑（terrain/deployable）全局静态，放在 episode.map 里只存一份；
            # 每步只留会变的"已占用格子"，避免 100 格 x N 步的 JSON 膨胀
            "occupiedCells": [c.cell_id for c in (state_before.game_map.cells
                                                  if state_before.game_map else [])
                              if c.occupied],
            "notes": list(state_before.notes or []),
            "vlm": {
                "situation": getattr(vlm, "situation", ""),
                "strategicAdvice": getattr(vlm, "strategicAdvice", "")
                or getattr(vlm, "strategic_advice", ""),
                "confidence": getattr(vlm, "confidence", 0.0),
                "level": getattr(vlm, "level", "inferred"),
                "analyzer": getattr(vlm, "analyzer", "mock"),
                "risks": list(getattr(vlm, "risks", []) or []),
            },
            # 喂给 LLM 的原始状态文本（复盘时可逐字对照）
            "stateText": pf.state_text,
        },
        # ---- 检索到的知识（带 evidence 分级）----
        "knowledge": {
            "query": knowledge.query,
            "contextText": knowledge.context_text,
            "citations": [dump(c) for c in knowledge.citations],
        },
        # ---- 慢思考 reasoning ----
        "reasoning": {
            "summary": decision.reasoning.summary,
            "analysis": list(decision.reasoning.analysis),
            "consideredActions": list(decision.reasoning.considered_actions),
            "risks": list(decision.reasoning.risks),
        },
        "decision": {
            "decisionId": decision.decision_id,
            "confidence": decision.confidence,
            "thinker": decision.thinker,
            "thoughtMs": round(float(decision.thought_ms), 3),
            "plan": dump(decision.plan),
        },
        # 桥接隐藏态本身（256 维 mock 伪向量）对回放无意义，只留元信息，避免 JSON 膨胀
        "bridge": {"decisionId": bridge.decision_id, "dim": bridge.dim,
                   "hint": bridge.hint, "source": bridge.source},
        "command": dump(command),
        "execute": dump(record.plan_result),
        "reflection": dump(reflection),
        # ---- 执行后读数与奖励 ----
        "after": {"cost": record.cost, "life": record.life},
        "reward": {"stepReward": step_reward, "items": [dump(i) for i in record.reward_items]},
        "evidence": [{"level": lv, "source": src}
                     for lv, _, src in ((e.partition(":")) for e in record.evidence)],
        "latencyMs": lat,
    }


def build_episode_dto(spec, log, steps, env, map_topology=None):
    """对局汇总（顶部概览区数据源）。"""
    bd = log.reward
    lat_keys = {}
    for s in steps:
        for k, v in s["latencyMs"].items():
            lat_keys.setdefault(k, 0.0)
            lat_keys[k] = round(lat_keys[k] + float(v or 0.0), 3)
    return {
        "id": spec["id"],
        "title": spec["title"],
        "stageId": log.stage_id,
        "backend": log.backend,
        "outcome": log.outcome,
        "outcomeLabel": OUTCOME_CN.get(log.outcome, log.outcome),
        "stepCount": len(log.steps),
        "durationSec": log.duration_sec,                 # 墙钟（真实运行耗时）
        "gameTimeSec": log.steps[-1].elapsed_sec if log.steps else 0.0,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": spec["source"],
        "reward": {
            "outcome": getattr(bd, "outcome", log.outcome),
            "total": getattr(bd, "total", 0.0),
            "winBonus": getattr(bd, "win_bonus", 0.0),
            "leakPenalty": getattr(bd, "leak_penalty", 0.0),
            "overcostPenalty": getattr(bd, "overcost_penalty", 0.0),
            "leaked": getattr(bd, "leaked", 0),
            "overcostSec": getattr(bd, "overcost_sec", 0.0),
            "lifeStart": getattr(bd, "life_start", None),
            "lifeEnd": getattr(bd, "life_end", None),
            "summaryLine": bd.summary_line() if hasattr(bd, "summary_line") else "",
            "items": [dump(i) for i in (getattr(bd, "items", None) or [])],
        },
        "totals": {
            "actionsTotal": sum((s["execute"] or {}).get("total", 0) for s in steps),
            "actionsSucceeded": sum((s["execute"] or {}).get("succeeded", 0) for s in steps),
            "actionsFailed": sum((s["execute"] or {}).get("failed", 0) for s in steps),
            "avgConfidence": round(sum(s["decision"]["confidence"] for s in steps)
                                   / len(steps), 3) if steps else 0.0,
            "latencySumMs": lat_keys,
        },
        "map": map_topology or {"cols": 0, "rows": 0, "cells": []},
        "maxSteps": env.max_steps,
        "stepDtSec": env.step_dt_sec,
    }


# ------------------------------------------------------------------ 原始日志
def render_raw_logs():
    """重新渲染两份原始文本日志（与 results/*.txt 同源同格式），供前端对照查看。"""
    from agent.decision_loop import build_mock_loop, render_decision_log, write_decision_log
    from env import render_episode_report
    from env.mock_env import run_mock_episode

    logs = []
    win = run_mock_episode("win", stage_id="3-8", win_in=10)
    lose = run_mock_episode("lose", stage_id="3-8", lose_in=3)
    logs.append({
        "id": "episode_report_win",
        "title": "对局报告（通关局）",
        "path": "results/episode_report_win.txt",
        "generatedBy": "scripts/smoke_env.py -> env.render_episode_report()",
        "text": render_episode_report(win),
    })
    logs.append({
        "id": "episode_report_lose",
        "title": "对局报告（失败局）",
        "path": "results/episode_report_lose.txt",
        "generatedBy": "scripts/smoke_env.py -> env.render_episode_report()",
        "text": render_episode_report(lose),
    })

    # 决策日志：用 DecisionLoop 跑 4 步（与 scripts/smoke_agent.py 默认步数一致）
    lines = []
    loop = build_mock_loop(log=lines.append)
    dlog = loop.run(stage_id="3-8", steps=4)
    path = write_decision_log(dlog, log_dir=os.path.join(ROOT, "results"))
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    logs.append({
        "id": "agent_decision_log",
        "title": "Agent 决策日志（可解释）",
        "path": "results/agent_decision_log.txt",
        "generatedBy": "scripts/smoke_agent.py -> agent.render_decision_log()",
        "text": text,
    })
    return logs


# ------------------------------------------------------------------ 入口
def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return os.path.getsize(path)


def main():
    ap = argparse.ArgumentParser(description="导出 mock 对局数据给 web/ 前端")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出目录（默认 web/src/mock）")
    ap.add_argument("--skip-raw-logs", action="store_true",
                    help="跳过原始文本日志导出（更快）")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    index = []
    for spec in EPISODES:
        doc = capture_episode(spec)
        size = write_json(os.path.join(args.out, "%s.json" % spec["id"]), doc)
        ep = doc["episode"]
        index.append({
            "id": ep["id"], "title": ep["title"], "stageId": ep["stageId"],
            "backend": ep["backend"], "outcome": ep["outcome"],
            "outcomeLabel": ep["outcomeLabel"], "stepCount": ep["stepCount"],
            "durationSec": ep["durationSec"], "gameTimeSec": ep["gameTimeSec"],
            "totalReward": ep["reward"]["total"], "generatedAt": ep["generatedAt"],
        })
        print("[export] %-14s %2d 步  结果=%-4s 总分=%+6.1f  %6.1f KB"
              % (ep["id"], ep["stepCount"], ep["outcome"], ep["reward"]["total"],
                 size / 1024.0))

    if not args.skip_raw_logs:
        logs = render_raw_logs()
        size = write_json(os.path.join(args.out, "rawLogs.json"), logs)
        print("[export] %-14s %d 份原始日志  %6.1f KB" % ("rawLogs", len(logs), size / 1024.0))

    payload = {
        "schemaVersion": 1,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "note": "由 web/scripts/export_mock.py 从仓库 mock 全链路导出，非手写数据；"
                "results/ 已 gitignore，改 mock 逻辑后请重新运行本脚本刷新。",
        "episodes": index,
    }
    write_json(os.path.join(args.out, "episodes.json"), payload)
    print("[export] 输出目录：%s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
