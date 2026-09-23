# 主决策循环：纯 CPU 编排，不依赖 GPU（GPU 推理封装在 slow/fast/bridge 内部，mock 下不加载）。
"""LLM Agent 主决策循环。

闭环（每步逐步打印日志，便于调试与可解释展示）：
    截屏/感知 -> 状态转文本 -> 知识检索(RAG+图谱) -> 慢思考(推理) -> 慢快桥接
    -> 快反应(即时可行性裁剪) -> 动作执行(ADB) -> 自我反思 -> 记录 StepRecord

组件全部以依赖注入传入（perception / knowledge / slow / bridge / fast / executor），
因此同一条循环既能在 CPU 用 mock 组件跑通，也能在 V100 替换为真实组件，循环代码不改。

- build_mock_loop()：装配一套自包含的 mock 组件（含会随部署演进的假战局），无 GPU/模拟器/
  爬虫数据即可跑通"状态→思考→决策→执行"。
- RAGGraphKnowledge：真实知识端口（KnowledgeService 懒加载，数据缺失时安全返回空）。
- render_decision_log()：把全过程渲染成带 reasoning 与 evidence 分级的可读决策日志。
"""

import os
import time
from typing import List, Optional

from .config import DEFAULT_CONFIG_PATH, load_agent_config
from .output_schema import (DecisionLog, KnowledgeBundle,
                            KnowledgeCitation, StepRecord)

__all__ = ["PerceptionFrame", "BasePerception", "MockPerception",
           "BaseKnowledge", "MockKnowledge", "RAGGraphKnowledge",
           "DecisionLoop", "build_mock_loop", "render_decision_log"]


# ---------------------------------------------------------------- 感知端口
class PerceptionFrame(object):
    """一次感知的产物（frame 为 numpy，不入 pydantic）。"""
    def __init__(self, frame, state, analysis, state_text):
        self.frame = frame
        self.state = state
        self.analysis = analysis
        self.state_text = state_text


class BasePerception(object):
    def perceive(self, elapsed_sec):
        # type: (float) -> PerceptionFrame
        raise NotImplementedError

    def on_after_step(self, command, plan_result):
        """一步执行结束后用真实执行结果更新内部战局（可选钩子）。"""
        pass


# ---------------------------------------------------------------- 知识端口
class BaseKnowledge(object):
    def gather(self, state):
        # type: (object) -> KnowledgeBundle
        raise NotImplementedError


class MockKnowledge(BaseKnowledge):
    """自包含 mock 知识：不依赖 data/ 下任何爬取数据，CI/离线可用。"""

    def gather(self, state):
        enemies = "、".join(e.name for e in state.enemies_on_field) or "未知敌人"
        query = "%s 敌人怎么应对（关卡 %s）" % (enemies, state.stage_id)
        citations = [
            KnowledgeCitation(
                source="PRTS攻略(mock)", doc_type="guide", evidence="retrieved",
                detail="重装敌人防御高、弱法术；高防单位宜用术师法伤处理（参考资料，需核实）"),
            KnowledgeCitation(
                source="知识图谱(mock)", doc_type="rule", evidence="inferred",
                detail="规则：高防(>=800)/高抗(>=50)敌人倾向术师/法伤与控制职业（推断，非事实）"),
        ]
        context = (
            "[retrieved] 攻略参考：%s\n"
            "[inferred] 图谱规则：%s" % (citations[0].detail, citations[1].detail))
        return KnowledgeBundle(query=query, context_text=context, citations=citations)


class RAGGraphKnowledge(BaseKnowledge):
    """真实知识端口：RAG 攻略(retrieved) + 关卡面板(fact) + 图谱推荐(inferred)。

    KnowledgeService 内部对向量库/图谱懒加载；数据缺失时各查询 found=False，
    这里据此安全返回空/部分结果，不抛异常。
    """

    def __init__(self, config_path=None):
        self.config_path = config_path
        self._service = None

    def _svc(self):
        if self._service is None:
            from knowledge.mcp_tools.service import KnowledgeService
            self._service = (KnowledgeService(self.config_path)
                             if self.config_path else KnowledgeService())
        return self._service

    def gather(self, state):
        svc = self._svc()
        stage_id = state.stage_id or ""
        enemies = [e.name for e in state.enemies_on_field]
        query = ("%s 怎么应对" % "、".join(enemies)) if enemies else ("%s 攻略" % stage_id)
        citations = []  # type: List[KnowledgeCitation]
        context_parts = []

        guide = svc.search_guide(query, k=5)
        if getattr(guide, "found", False):
            for h in guide.hits[:3]:
                citations.append(KnowledgeCitation(
                    source="RAG", detail=h.content[:120], evidence="retrieved",
                    doc_type=h.doc_type, url=h.url, score=h.score))
            context_parts.append("[retrieved] " + " / ".join(
                (h.source + ": " + h.content[:80]) for h in guide.hits[:3]))

        if stage_id:
            stage = svc.query_stage(stage_id)
            if getattr(stage, "found", False):
                names = "、".join(e.name for e in stage.enemies)
                citations.append(KnowledgeCitation(
                    source="PRTS", detail="关卡 %s 敌情：%s" % (stage_id, names),
                    evidence="fact", doc_type="stage", url=stage.source_url))
                context_parts.append("[fact] 关卡面板敌情：" + names)
            rec = svc.recommend_operators(stage_id)
            if getattr(rec, "found", False) and rec.operators:
                ops = "、".join(o.operator for o in rec.operators[:5])
                citations.append(KnowledgeCitation(
                    source="知识图谱", detail="本关按克制规则推荐：%s" % ops,
                    evidence="inferred", doc_type="recommend"))
                context_parts.append("[inferred] 图谱推荐(规则,非事实)：" + ops)

        return KnowledgeBundle(
            query=query, context_text="\n".join(context_parts), citations=citations)


# ---------------------------------------------------------------- 可演进 mock 感知
class MockPerception(BasePerception):
    """随对局推进而变化的假战局：费用回复、部署后干员离场/占格，驱动 Agent 做出不同决策。"""

    def __init__(self, stage_id="3-8"):
        from perception.state_parser import MockStateParser
        self.stage_id = stage_id
        self._builder = MockStateParser(stage_id=stage_id)
        self.cost = 6
        self.regen_per_tick = 3
        # name -> (class, cost, slot)
        self.roster = {
            "翎羽": ("先锋", 2, 0),
            "克洛丝": ("狙击", 3, 1),
            "安赛尔": ("医疗", 3, 2),
        }
        self.deployed = {"芬": "E4"}       # name -> cell
        self.occupied = set()             # 本 mock 部署占用的 A/B 格

    def perceive(self, elapsed_sec):
        from perception.schemas import DeployedOperator, OperatorCard
        from perception.screen_capture import MockScreenCapture
        from perception.state_to_text import state_to_text
        from perception.vlm_analyzer import MockVLMAnalyzer

        frame, meta = MockScreenCapture().capture_with_meta()
        state = self._builder.get_state(elapsed_sec=elapsed_sec, frame_meta=meta)

        # 用"演进中"的战局覆盖 builder 的固定快照
        state.cost = self._cost_status()
        state.operator_cards = [
            OperatorCard(name=n, operator_class=cls, cost=cost, slot=slot)
            for n, (cls, cost, slot) in self.roster.items()]
        deployed = []
        for n, cell in self.deployed.items():
            deployed.append(DeployedOperator(
                name=n, cell_id=cell,
                direction="left", hp_ratio=1.0))
        state.deployed = deployed
        state.deploy_used = len(deployed)
        if state.game_map is not None:
            for cell in state.game_map.cells:
                if cell.cell_id in self.occupied:
                    cell.occupied = True
        analysis = MockVLMAnalyzer().analyze(frame, state)
        return PerceptionFrame(frame, state, analysis, state_to_text(state, analysis))

    def _cost_status(self):
        from perception.schemas import CostStatus
        return CostStatus(current=self.cost, limit=99, confidence=1.0, source="mock")

    def card_slot(self, name):
        info = self.roster.get(name)
        return info[2] if info else None

    def deployed_cell(self, name):
        return self.deployed.get(name)

    def on_after_step(self, command_or_plan, plan_result):
        # 兼容 FastCommand（含 .plan）与直接传入的 ActionPlan（env 调度用）。
        # 只对真正执行成功的部署生效：干员离手牌、占格、扣费用。
        plan = getattr(command_or_plan, "plan", command_or_plan)
        actions = getattr(plan, "actions", [])
        for act, res in zip(actions, plan_result.results):
            if act.action == "deploy" and res.success:
                info = self.roster.pop(act.operator_id, None)
                if info is not None:
                    self.deployed[act.operator_id] = act.grid_pos
                    self.occupied.add(act.grid_pos)
                    self.cost = max(0, self.cost - info[1])

    def regen(self):
        self.cost += self.regen_per_tick


# ---------------------------------------------------------------- 决策循环
class DecisionLoop(object):
    def __init__(self, perception, knowledge, slow, bridge, fast, executor,
                 config=None, config_path=DEFAULT_CONFIG_PATH, log=None):
        self.perception = perception
        self.knowledge = knowledge
        self.slow = slow
        self.bridge = bridge
        self.fast = fast
        self.executor = executor
        self.config = config or load_agent_config(config_path)
        self.backend = self.config.get("backend", "mock")
        self.do_reflect = bool(self.config["loop"].get("reflect", True))
        self.tick_interval_ms = int(self.config["loop"].get("tick_interval_ms", 0))
        self.log_dir = self.config["loop"].get("log_dir", "results")
        self._say = log or print
        self._last_reflection = None  # type: Optional[object]

    def run(self, stage_id="3-8", steps=None):
        # type: (str, Optional[int]) -> DecisionLog
        steps = steps or int(self.config["loop"].get("max_steps", 6))
        decision_log = DecisionLog(stage_id=stage_id, backend=self.backend)
        self._say("=" * 72)
        self._say("Agent 决策循环开始（backend=%s, steps=%d, stage=%s）"
                  % (self.backend, steps, stage_id))
        for tick in range(steps):
            elapsed = 6.0 * tick
            if tick > 0 and hasattr(self.perception, "regen"):
                self.perception.regen()
            record = self._step(tick, elapsed, stage_id)
            decision_log.steps.append(record)
            if self.tick_interval_ms:
                time.sleep(self.tick_interval_ms / 1000.0)
        decision_log.finished_ts = time.time()
        self._say("=" * 72)
        self._say("决策循环结束：共 %d 步，下发动作 %d 个，失败 %d 个。"
                  % (len(decision_log.steps), decision_log.total_actions(),
                     decision_log.failed_actions()))
        return decision_log

    def _step(self, tick, elapsed_sec, stage_id):
        # type: (int, float, str) -> StepRecord
        lat = {}
        t0 = time.time()
        pf = self.perception.perceive(elapsed_sec)
        lat["perceive_ms"] = round((time.time() - t0) * 1000.0, 1)

        t = time.time()
        knowledge = self.knowledge.gather(pf.state)
        lat["knowledge_ms"] = round((time.time() - t) * 1000.0, 1)

        t = time.time()
        decision = self.slow.think(
            stage_id=stage_id, elapsed_sec=elapsed_sec, state_text=pf.state_text,
            knowledge=knowledge, reflection=self._last_reflection, state=pf.state)
        lat["slow_ms"] = round((time.time() - t) * 1000.0, 1)

        t = time.time()
        bridge_state = self.bridge.project(decision)
        lat["bridge_ms"] = round((time.time() - t) * 1000.0, 1)

        t = time.time()
        command = self.fast.react(pf.state, decision, bridge_state)
        lat["fast_ms"] = round((time.time() - t) * 1000.0, 1)

        t = time.time()
        plan_result = self.executor.execute(command.plan)
        lat["execute_ms"] = round((time.time() - t) * 1000.0, 1)

        if hasattr(self.perception, "on_after_step"):
            self.perception.on_after_step(command, plan_result)

        reflection = None
        if self.do_reflect:
            reflection = self.slow.reflect(decision, plan_result, pf.state_text)
            self._last_reflection = reflection

        record = StepRecord(
            step=tick, elapsed_sec=elapsed_sec, state_excerpt=pf.state_text,
            knowledge=knowledge, decision=decision, bridge=bridge_state,
            command=command, execute=plan_result, reflection=reflection,
            latency_ms=lat)
        self._log_step(record)
        return record

    def _log_step(self, r):
        d, c, pr = r.decision, r.command, r.execute
        self._say("-" * 72)
        self._say("[步 %d | t=%.0fs] 慢思考(%.0fms conf=%.2f) -> 快反应(%.0fms) -> 执行"
                  % (r.step, r.elapsed_sec, d.thought_ms, d.confidence, c.react_ms))
        for line in d.reasoning.analysis:
            self._say("    思考: " + line)
        if d.reasoning.risks:
            self._say("    风险: " + "；".join(d.reasoning.risks))
        if r.knowledge.citations:
            self._say("    引用: " + "；".join(
                "[%s]%s" % (k.evidence, k.source) for k in r.knowledge.citations))
        if c.dropped:
            self._say("    快通道拦截: " + "；".join(c.dropped))
        for ar in pr.results:
            self._say("    执行 #%d %-7s %s %s" % (
                ar.index, ar.action, "OK " if ar.success else "FAIL",
                "->".join(ar.ops) if ar.success else ar.error))
        if r.reflection is not None:
            self._say("    反思[%s]: %s" % (r.reflection.verdict,
                                           r.reflection.adjustment))


# ---------------------------------------------------------------- 装配 mock 全链路
def build_mock_loop(config_path=DEFAULT_CONFIG_PATH, log=None):
    """装配一套自包含 mock 组件（含动作执行器，resolver 实时读取演进中的 mock 战局）。"""
    from action.adb_controller import MockADBController
    from action.action_executor import ActionExecutor
    from action.config import load_action_config
    from .fast_reactor import MockFastReactor
    from .latent_bridge import MockLatentBridge
    from .slow_thinker import MockSlowThinker

    cfg = load_agent_config(config_path)
    perception = MockPerception()
    executor = ActionExecutor(
        MockADBController(), config=load_action_config(),
        card_slot_resolver=perception.card_slot,
        deployed_cell_resolver=perception.deployed_cell,
        real_sleep=False)
    return DecisionLoop(
        perception=perception, knowledge=MockKnowledge(),
        slow=MockSlowThinker(config=cfg), bridge=MockLatentBridge(config=cfg),
        fast=MockFastReactor(config=cfg), executor=executor,
        config=cfg, log=log)


# ---------------------------------------------------------------- 可解释日志渲染
def render_decision_log(decision_log):
    # type: (DecisionLog) -> str
    L = []
    L.append("# arknights-llm-agent 决策日志（可解释）")
    L.append("关卡=%s backend=%s 步数=%d 动作合计=%d 失败=%d" % (
        decision_log.stage_id, decision_log.backend, len(decision_log.steps),
        decision_log.total_actions(), decision_log.failed_actions()))
    for r in decision_log.steps:
        d, c, pr = r.decision, r.command, r.execute
        L.append("")
        L.append("=" * 68)
        L.append("步 %d | 对局 t=%.0fs | 延迟 %s" % (
            r.step, r.elapsed_sec,
            " ".join("%s=%.0f" % (k, v) for k, v in r.latency_ms.items())))
        L.append("-- 状态（喂给 LLM）--")
        L.append(r.state_excerpt)
        if r.knowledge.citations:
            L.append("-- 检索知识 --")
            for k in r.knowledge.citations:
                L.append("  * [%s] %s: %s" % (k.evidence, k.source, k.detail))
        L.append("-- 慢思考 reasoning (%s) --" % d.thinker)
        L.append("  结论: %s" % d.reasoning.summary)
        for i, a in enumerate(d.reasoning.analysis, 1):
            L.append("  依据%d: %s" % (i, a))
        for ca in d.reasoning.considered_actions:
            L.append("  取舍: %s" % ca)
        for risk in d.reasoning.risks:
            L.append("  风险: %s" % risk)
        L.append("  置信度: %.2f | 思考耗时: %.0fms" % (d.confidence, d.thought_ms))
        if r.bridge is not None:
            L.append("-- 慢快桥接 --")
            L.append("  %s（dim=%d, source=%s）" % (
                r.bridge.hint, r.bridge.dim, r.bridge.source))
        L.append("-- 快反应 (%s) conf=%.2f --" % (c.reactor, c.confidence))
        L.append("  " + c.note)
        for drop in c.dropped:
            L.append("  拦截: " + drop)
        L.append("-- 执行 --")
        for ar in pr.results:
            L.append("  #%d %-7s %s %s" % (
                ar.index, ar.action, "成功" if ar.success else "失败(" + ar.status + ")",
                "->".join(ar.ops) if ar.success else ar.error))
        if r.reflection is not None:
            L.append("-- 自我反思 [%s] --" % r.reflection.verdict)
            for issue in r.reflection.issues:
                L.append("  问题: " + issue)
            L.append("  修正: " + r.reflection.adjustment)
    return "\n".join(L)


def write_decision_log(decision_log, path=None, log_dir="results"):
    # type: (DecisionLog, Optional[str], str) -> str
    if path is None:
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "agent_decision_log.txt")
    text = render_decision_log(decision_log)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# generated at %s\n\n%s\n" % (
            time.strftime("%Y-%m-%d %H:%M:%S"), text))
    return path
