#!/usr/bin/env python3
"""mock 全链路冒烟（CPU，无 GPU/模拟器/真实游戏数据）。

视觉链路（第三批）：截屏(Mock) -> OCR费用(Mock) + 地图解析(Mock,缓存) ->
  状态组装(SpawnTracker 波次推算 + YOLO confirm_spawn 敌情确认) -> VLM 慢通道(Mock)
  -> state_to_text 状态报告。
动作链路（第四批）：状态报告后用一段占位 ActionPlan 走 MockActionExecutor，
  编译并下发 tap/swipe/wait，验证"状态 -> 动作 -> ADB 原语"编排与容错。

运行（在仓库根）：python scripts/smoke_perception.py
退出码 0 表示链路与关键信息完整；非 0 表示回归失败。
"""

import os
import sys
import time

# 允许从 scripts/ 直接运行：把仓库根加入 sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import numpy as np  # noqa: E402

from perception.map_parser import MockMapParser  # noqa: E402
from perception.ocr_cost import MockOCRCostReader  # noqa: E402
from perception.schemas import (DeployedOperator, OperatorCard,  # noqa: E402
                                SkillStatus)
from perception.screen_capture import MockScreenCapture  # noqa: E402
from perception.state_parser import SpawnTracker, StateParser  # noqa: E402
from perception.detector_yolo import MockDetector  # noqa: E402
from perception.state_to_text import state_to_text  # noqa: E402
from perception.vlm_analyzer import MockVLMAnalyzer  # noqa: E402

from action import Action, ActionPlan, MockActionExecutor  # noqa: E402

STAGE_ID = "3-8"
ELAPSED = 12.0


def main():
    print("=" * 72)
    print("arknights-llm-agent 视觉 mock 全链路冒烟（第三批）")
    print("=" * 72)

    # 1) 截屏（确定性合成帧）
    cap = MockScreenCapture()
    frame, meta = cap.capture_with_meta()
    print("[1/7] 截屏: frame=%s source=%s" % (frame.shape, meta.source))

    # 2) OCR 费用（连续两帧一致 -> 稳定）
    ocr = MockOCRCostReader(values=[15, 15])
    ocr.read(frame)
    cost = ocr.read(frame)
    print("[2/7] OCR 费用: %d (state=%s)" % (cost.current, cost.state))

    # 3) 地图（开局静态布局，缓存；E4 已部署芬 -> 占用回写）
    mapper = MockMapParser()
    game_map = mapper.parse(cache_key=STAGE_ID)
    game_map = mapper.set_occupied(["E4"], cache_key=STAGE_ID)
    print("[3/7] 地图: %dx%d, 可部署 %d 格（缓存键=%s）" % (
        game_map.cols, game_map.rows, len(game_map.deployable_ids()), STAGE_ID))

    # 4) 手牌/已部署/技能（mock 固定阵容）
    cards = [
        OperatorCard(name="翎羽", operator_class="先锋", cost=2, slot=0),
        OperatorCard(name="克洛丝", operator_class="狙击", cost=3, slot=1),
        OperatorCard(name="安赛尔", operator_class="医疗", cost=3, slot=2),
    ]
    deployed = [DeployedOperator(name="芬", cell_id="E4", direction="left", hp_ratio=1.0)]
    skills = [SkillStatus(operator="芬", slot=0, ready=False, active=False,
                          sp_text="0/10", source="mock")]

    # 5) 敌情：敌情表 + 计时推算 + YOLO 出现确认
    stage_info = {"enemies": [
        {"名称": "源石虫", "数量": 3},
        {"名称": "猎犬", "数量": 2},
        {"名称": "重装敌人", "数量": 3},
    ]}
    tracker = SpawnTracker()
    detector = MockDetector()  # 默认在左侧入场 ROI 检出 3 个重装敌人
    # 先建计划拿敌人名单，再逐名做 confirm_spawn（第一版 YOLO 只确认出现）
    plan, _ = tracker.build_plan(STAGE_ID, stage_info)
    confirmations = {p.enemy: detector.confirm_spawn(p.enemy, frame) for p in plan}
    print("[4/7] 敌情确认: %s" % confirmations)

    state = StateParser().parse(
        frame_meta=meta, stage_id=STAGE_ID, elapsed_sec=ELAPSED,
        spawn_tracker=tracker, stage_info=stage_info, cost=cost,
        operator_cards=cards, deployed=deployed, skills=skills, game_map=game_map,
        life_points=3, deploy_used=1, deploy_limit=9, confirmations=confirmations)
    # mock：本关敌人统一从左侧入场（真机由地图入口/视觉给出）
    for e in state.enemies_on_field:
        e.position_hint = "左侧"
    print("[5/7] 状态组装: 场上敌人 %d 类, timing=%s" % (
        len(state.enemies_on_field), state.timing_source))

    # 6) VLM 慢通道 + 状态文本
    analysis = MockVLMAnalyzer().analyze(frame, state)
    report = state_to_text(state, analysis)
    print("[6/7] VLM 分析完成（%s, conf=%.2f）" % (analysis.analyzer, analysis.confidence))

    print("\n" + "-" * 72)
    print("游戏状态报告")
    print("-" * 72)
    print(report)
    print("-" * 72)

    # 落一份到 results/（gitignore），方便人工检查
    os.makedirs("results", exist_ok=True)
    out_path = os.path.join("results", "perception_smoke_report.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# generated at %s\n\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), report))
    print("报告已写入: %s" % out_path)

    # ---- [7] 动作执行（mock）：用一段占位决策把"状态 -> 动作 -> ADB 原语"跑通 ----
    # 说明：第五批 LLM 才真正据状态决策；这里用固定 ActionPlan 验证 action 层编排与容错。
    print("\n[7/7] 动作执行（mock，占位决策；真实决策由第五批 Agent 给出）")
    executor = MockActionExecutor(
        card_slots={"翎羽": 0, "克洛丝": 1, "安赛尔": 2},
        deployed_cells={"芬": "E4"})
    plan = ActionPlan(actions=[
        Action(action="deploy", operator_id="翎羽", grid_pos="A2", direction="left"),
        Action(action="wait", duration_ms=200),
        Action(action="retreat", operator_id="芬"),
    ], reason="mock：先下先锋回费（占位，真机由 LLM 决策）")
    plan_res = executor.execute(plan)
    for r in plan_res.results:
        print("    #%d %-8s %s %s" % (
            r.index, r.action, "OK " if r.success else "FAIL",
            "->".join(r.ops) if r.success else r.error))
    print("    设备原语序列: %s" % " -> ".join(executor.device_ops()))

    # ---- 关键完整性断言（回归闸门）----
    deploy_ops = plan_res.results[0].ops
    checks = {
        "费用15": "费用 15" in report,
        "稳定标签": "[稳定]" in report,
        "三个手牌": all(n in report for n in ("翎羽", "克洛丝", "安赛尔")),
        "已部署E4": "芬@E4朝左" in report,
        "重装敌人": "重装敌人 x3" in report,
        "重装经CV确认": "重装敌人 x3 [CV确认]" in report,
        "估算波次标签": "[计时估算]" in report,
        "可部署10格": "可部署10格" in report,
        "VLM局势": "【VLM局势】" in report and "术师" in report,
        "证据-retrieved": "retrieved(RAG参考资料" in report,
        "证据-inferred": "inferred(规则/模型推断" in report,
        "估算值备注": "估算值" in report,
        "动作全成功": plan_res.all_success,
        "部署含点卡+滑动": deploy_ops[0] == "tap" and "swipe" in deploy_ops,
        "撤退点两次": plan_res.results[2].ops.count("tap") == 2,
    }
    failed = [k for k, ok in checks.items() if not ok]
    print("\n完整性检查: %d/%d 通过" % (len(checks) - len(failed), len(checks)))
    if failed:
        print("未通过项: %s" % failed)
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
