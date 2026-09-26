# -*- coding: utf-8 -*-
# SFT 数据准备（纯 CPU，可在无 GPU/无 PRTS 语料时降级运行）。
# 把 MAA 作业(maa-copilot 抄作业 schema 子集)的动作时间轴 + PRTS 关卡/干员语料，
# 反推出 {"question": 状态描述, "answer": 决策+理由} 的指令微调对。
#
# 重要诚实性约定：
# - 作业里的"在击杀X/费用Y时对谁做什么"是**事实**（evidence=fact，来源 maa_job）；
# - PRTS 的干员属性/关卡敌情是**事实**（evidence=fact，来源 prts）；
# - "为什么这一步这么做"是我们从时间轴+职业机制**反推**的（evidence=inferred,
#   来源 timeline_reconstructed），不是作业作者原话，训练/使用时不得当成专家确证理由。
"""SFT 数据准备：MAA 作业 + PRTS 语料 -> question/answer JSONL。"""

import argparse
import glob
import json
import os
import random
import re

from .config import load_training_config

__all__ = [
    "load_maa_job", "build_prts_index", "build_examples", "write_jsonl",
    "prepare_jobs", "group_split_by_stage", "SUPPORTED_ACTIONS",
]

# MAA 动作类型 -> 本项目 action 词表（与 action/action_space.py 对齐）
SUPPORTED_ACTIONS = {"部署": "deploy", "技能": "skill", "撤退": "retreat"}
DIRECTIONS = ("上", "下", "左", "右")

# “职业泛称/占位”干员名：部分作业作者不写具体干员，而用职业/分支/黑话占灵活位
# （如 输出/奶盾/单奶/快活），或 MAA 空槽哨兵 Unknown_EndsEmpty。这类动作不是可执行的
# 具体策略，SFT 中剔除（计数为“泛称占位干员”）。只收无歧义词，宁漏勿错；
# 疑似具体召唤物/装置昵称（如 地刺/书刀/祖宗）不在此表，保留。
GENERIC_OPERATOR_TOKENS = {
    # 八大职业
    "先锋", "近卫", "医疗", "术师", "术士", "重装", "狙击", "辅助", "特种",
    # 通用泛称
    "奶", "盾", "输出", "奶盾", "工具人", "挡", "前排", "后排", "主C", "副C",
    # 医疗分支/黑话
    "单奶", "群奶", "奶妈", "元素奶", "行医", "奶医",
    # 术师/狙击/先锋/近卫 分支黑话
    "单法", "群法", "速狙", "快狙", "群狙", "投锋", "领主", "快活",
}
_SENTINEL_RE = re.compile(r"unknown|endsempty|^none$|^null$", re.IGNORECASE)
# MAA“灵活位”需求文本的**结构**判据（零误伤：真实干员/召唤物/装置名都不会命中）：
#   1) 含练度要求括号或关键词：【医师】…练度 / 医疗：精一满级及以上
#   2) “职业-分支”占位：特种-伏击客 / 重装-守护者（右侧限 2-6 个汉字，排除联动 Latin 名）
#   3) “职业+编号”占位：医疗2 / 铁卫1 / 先锋二
#   4) “短词：练度要求”：地刺：精一满级及以上（御龙：雷狼龙等真实名因无练度词不命中）
_CLASS_HEAD = r"(?:先锋|近卫|医疗|术师|术士|重装|狙击|辅助|特种|铁卫|奶|盾)"
_FLEX_PATTERNS = (
    re.compile(r"[【】]|练度|精[一二三123]|满级|及以上|专[一二三1-3]"),
    re.compile(r"^(?:先锋|近卫|医疗|术师|术士|重装|狙击|辅助|特种|铁卫)\s*[-—–]\s*[一-鿿]{2,6}$"),
    re.compile(r"^%s\s*[0-9０-９一二三四五六七八九十]+\)?$" % _CLASS_HEAD),
    re.compile(r"^.{1,8}\s*[：:]\s*.*(?:精[一二三123]|满级|练度|级及以上)"),
)


def is_generic_operator(name):
    # type: (str) -> bool
    if not name:
        return False
    raw = str(name)
    norm = raw.strip().strip("“”\"' ")
    if norm in GENERIC_OPERATOR_TOKENS or raw in GENERIC_OPERATOR_TOKENS:
        return True
    if _SENTINEL_RE.search(norm):
        return True
    return any(p.search(norm) for p in _FLEX_PATTERNS)


# ---------------------------------------------------------------- 加载
def load_maa_job(path):
    # type: (str) -> dict
    with open(path, "r", encoding="utf-8") as f:
        job = json.load(f)
    stage_name = job.get("stage_name")
    details = job.get("details") or {}
    actions = details.get("actions")
    if not stage_name or not isinstance(stage_name, str):
        raise ValueError("MAA 作业缺少 stage_name：%s" % path)
    if not isinstance(actions, list) or not actions:
        raise ValueError("MAA 作业缺少非空 details.actions：%s" % path)
    return job


def build_prts_index(prts_dir):
    # type: (str) -> tuple
    """返回 (stage_by_code, op_by_name)。目录不存在/为空时返回 ({}, {}) 以便降级。"""
    stages = {}
    ops = {}
    if not prts_dir or not os.path.isdir(prts_dir):
        return stages, ops
    for p in glob.glob(os.path.join(prts_dir, "stages", "*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (ValueError, OSError) as exc:
            print("[sft_prep] 跳过损坏的关卡 JSON：%s（%s）" % (p, exc))
            continue
        code = d.get("code")
        if code:
            stages[str(code)] = d
    for p in glob.glob(os.path.join(prts_dir, "operators", "*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (ValueError, OSError) as exc:
            print("[sft_prep] 跳过损坏的干员 JSON：%s（%s）" % (p, exc))
            continue
        name = d.get("name")
        if name:
            ops[str(name)] = d
    return stages, ops


def _prts_stage_candidates(stage_id):
    # type: (str) -> list
    """MAA 作业 stage_name -> 可能对应的 PRTS 关卡 code（按优先级）。

    MAA 用内部标识（正常主线 main_03-08，可带 #f# 等模式后缀），PRTS 用展示 code（3-8）。
    只对“正常主线 main_”做去零填充映射；tough_/hard_/easy_/sub_ 等是磨难/险地/支线变体，
    敌情与正常关未必一致，不强行挂到普通关，避免把错误敌情当事实。
    """
    sid = str(stage_id or "").split("#")[0].strip()
    cands = []
    if sid:
        cands.append(sid)
    m = re.match(r"^main_(\d{1,2})-(\d{1,2})$", sid)
    if m:
        cands.append("%d-%d" % (int(m.group(1)), int(m.group(2))))  # main_03-08 -> 3-8
    # 去重保序
    seen = set()
    return [c for c in cands if not (c in seen or seen.add(c))]


# ---------------------------------------------------------------- 工具
def _loc_text(loc):
    if isinstance(loc, (list, tuple)) and len(loc) == 2:
        return "(%d,%d)" % (int(loc[0]), int(loc[1]))
    return "位置未知"


def _enemy_line(e):
    name = e.get("名称", "?")
    role = e.get("地位", "")
    lv = e.get("级别", "")
    dfn = e.get("防御力", "")
    cnt = e.get("数量", "")
    tags = []
    if role:
        tags.append(role)
    if lv not in ("", None):
        tags.append("lv%s" % lv)
    if dfn not in ("", None, "—"):
        tags.append("防%s" % dfn)
    if cnt not in ("", None):
        tags.append("x%s" % cnt)
    return name + (（"（%s）" % "/".join(tags)) if tags else "")


def _high_def_enemy_names(stage_json, threshold=150):
    """挑出高物理防御敌人名（整数防御>=阈值），用于术师部署理由；无法解析则忽略。"""
    names = []
    for e in stage_json.get("enemies", []) or []:
        try:
            dfn = int(str(e.get("防御力", "0")).replace(",", ""))
        except (ValueError, TypeError):
            continue
        if dfn >= threshold and e.get("名称"):
            names.append("%s(防%d)" % (e["名称"], dfn))
    return names


def _operator_skill_names(op_json):
    out = []
    for sk in op_json.get("skills", []) or []:
        nm = sk.get("name")
        if nm:
            out.append(nm)
    return out


# ---------------------------------------------------------------- 状态/理由构造
def _state_question(stage_code, stage_json, kills, cost, deployed, prts_ok):
    # type: (...) -> str
    L = ["[关卡] %s" % stage_code]
    if stage_json is not None:
        normal = stage_json.get("normal", {}) or {}
        # 顶层 name 是干净的“编号 中文名”；normal.name 在部分新章节（磨难/险地难度选择器
        # 布局）会混入整段 UI 文案（难度/理智/掉落，可达数百字），故优先顶层 name。
        sname = stage_json.get("name") or normal.get("name") or ""
        L[0] = "[关卡] %s" % (("%s %s" % (stage_code, sname)).strip())
        facts = []
        for label, key in (("目标点耐久", "目标点耐久"), ("初始费用", "初始COST"),
                           ("费用上限", "COST上限"), ("部署上限", "部署上限")):
            if normal.get(key):
                facts.append("%s=%s" % (label, normal[key]))
        if facts:
            L.append("[关卡参数] " + "，".join(facts))
        enemies = stage_json.get("enemies", []) or []
        if enemies:
            L.append("[本关敌情·fact@PRTS] " + "；".join(_enemy_line(e) for e in enemies))
    elif not prts_ok:
        L.append("[本关敌情] 无 PRTS 语料（本样本仅依据作业时间轴构造）")

    prog = "[进度] 已击杀 %d 个敌人；" % int(kills)
    prog += ("当前费用约 %s。" % cost) if cost not in (None, "") else "当前费用以击杀数为锚。"
    L.append(prog)

    if deployed:
        def _dep(n, v):
            face = ("朝%s" % v[1]) if (v and len(v) > 1 and v[1] in DIRECTIONS) else "（无朝向）"
            return "%s%s%s" % (n, _loc_text(v[0] if v else None), face)
        L.append("[已部署] " + "；".join(_dep(n, v) for n, v in deployed.items()))
    else:
        L.append("[已部署] 无")
    L.append("[任务] 给出下一步动作与理由（动作词表：deploy/skill/retreat/wait）。")
    return "\n".join(L)


def _rationale(act_type, a, op_json, stage_json, deployed, prts_ok):
    # type: (...) -> tuple
    """返回 (理由列表, evidence_dict)。理由是推断；属性/敌情是事实。"""
    name = a.get("name")
    kills = a.get("kills")
    reasons = []
    trig = "作业在已击杀%s%s时触发该动作" % (
        kills, ("、费用约%s" % a["cost_changes"]) if a.get("cost_changes") not in (None, "") else "")
    evidence = {"action": "fact:maa_job",
                "rationale": "inferred:timeline_reconstructed"}

    cls = branch = trait_desc = None
    if op_json is not None:
        meta = op_json.get("meta", {}) or {}
        cls = meta.get("class")
        branch = meta.get("branch")
        trait_desc = (op_json.get("trait", {}) or {}).get("描述")
        evidence["operator"] = "fact:prts"
    if stage_json is not None:
        evidence["enemies"] = "fact:prts"

    who = "%s（%s/%s）" % (name, cls, branch) if (cls and name) else (name or "该单位")
    if act_type == "deploy":
        d = a.get("direction")
        face = "朝%s" % d if d in DIRECTIONS else "（无朝向放置物）"
        reasons.append("部署 %s 于%s%s——%s（动作来自作业时间轴）" % (
            who, _loc_text(a.get("location")), face, trig))
        if cls == "先锋":
            reasons.append("先锋前期下场站场并承担回复/产费职责，为后续高费干员争取费用")
        elif cls == "医疗":
            cur = "、".join(deployed.keys()) if deployed else "前排"
            reasons.append("部署医疗为已上场干员（%s）提供治疗，维持阵线血量" % cur)
        elif cls == "狙击":
            tip = "，%s" % trait_desc if trait_desc else ""
            reasons.append("狙击提供远程物理输出，补足阵线伤害%s" % tip)
        elif cls == "术师":
            hd = _high_def_enemy_names(stage_json) if stage_json else []
            if hd:
                reasons.append("术师造成法术伤害、不被高物理防御减免；本关含高防敌人 "
                               + "、".join(hd[:4]) + "（fact@PRTS），需法术应对")
            else:
                reasons.append("术师造成法术伤害，补足对高防目标的输出")
        elif cls == "重装":
            reasons.append("重装高阻挡数，前压拦阻敌人、保护目标点")
        elif cls == "近卫":
            reasons.append("近卫近战持续输出并兼顾阻挡，补足正面伤害、稳住阵线")
        elif cls == "辅助":
            tip = "，%s" % trait_desc if trait_desc else ""
            reasons.append("辅助提供减速/削弱/增益等控场，为输出干员创造输出环境%s" % tip)
        elif cls == "特种":
            reasons.append("特种承担快速复活、推拉位移或特殊控场，针对当前敌人机制做功能性处理")
        elif op_json is None:
            # 无 PRTS 干员卡的多为装置/障碍物/召唤物
            reasons.append("按作业时机放置该装置/召唤物，提供场地效果或额外阻挡")
        else:
            reasons.append("按作业要求在此节点补齐阵容")
    elif act_type == "skill":
        skill_names = _operator_skill_names(op_json) if op_json else []
        skill_hint = ("技能候选：%s；" % "、".join(skill_names)) if skill_names else ""
        reasons.append("开启 %s 的技能——%s（动作来自作业时间轴）" % (name, trig))
        reasons.append(skill_hint + "波次压力上升时用技能提升爆发/续航，应对当前接敌")
    elif act_type == "retreat":
        target = name if name else ("%s 上的单位" % _loc_text(a.get("location")))
        reasons.append("撤退 %s——%s（动作来自作业时间轴）" % (target, trig))
        reasons.append("释放部署位/部分费用并进入再部署循环，为后续关键节点腾挪资源")
    return reasons, evidence


# ---------------------------------------------------------------- 主构造
def build_examples(job, prts_dir=None, stage_json=None, op_index=None,
                   stage_index=None):
    # type: (dict, str, object, object, dict) -> tuple
    if stage_index is not None:
        stages = stage_index
        ops = {}
    elif prts_dir is not None and stage_json is None:
        stages, ops = build_prts_index(prts_dir)
    else:
        stages, ops = {}, {}
    if op_index is not None:
        ops = op_index
    stage_code = str(job.get("stage_name"))
    if stage_json is None:
        for cand in _prts_stage_candidates(stage_code):
            if cand in stages:
                stage_json = stages[cand]
                break
    prts_ok = bool(stage_json)  # 关键语料在否（干员可缺失，关卡为主）

    details = job.get("details", {}) or {}
    actions = details.get("actions", [])
    deployed = {}   # name -> [loc, direction]
    examples = []
    skipped = {}    # raw_type -> count

    for idx, a in enumerate(actions):
        raw_type = a.get("type")
        act_type = SUPPORTED_ACTIONS.get(raw_type)
        if act_type is None:
            skipped[raw_type] = skipped.get(raw_type, 0) + 1
            continue
        name = a.get("name")
        op_json = ops.get(name) if name else None
        kills = a.get("kills", 0)
        cost = a.get("cost_changes")

        # 部署/技能必须具名才是可学习样本（上传者漏填名字的动作为噪声，跳过）；
        # 撤退允许按格子（name 为空、location 有效）。
        if act_type in ("deploy", "skill") and not name:
            skipped[raw_type + "_无名"] = skipped.get(raw_type + "_无名", 0) + 1
            continue
        # 具名但属于“职业泛称/空槽哨兵”（输出/奶盾/Unknown_EndsEmpty 等）一律不可执行，剔除；
        # 撤退仅在具名时才需要校验（按格撤退不经过干员名）。
        if name and is_generic_operator(name):
            skipped["泛称占位干员"] = skipped.get("泛称占位干员", 0) + 1
            continue

        question = _state_question(stage_code, stage_json, kills, cost,
                                   deployed, prts_ok)
        reasons, evidence = _rationale(act_type, a, op_json, stage_json,
                                       deployed, prts_ok)
        # 答案：先一句动作，再列理由
        if act_type == "deploy":
            d = a.get("direction")
            who_name = name or _loc_text(a.get("location"))
            if d in DIRECTIONS:
                head = "deploy %s at %s facing %s" % (
                    who_name, _loc_text(a.get("location")), d)
            else:
                # 障碍物/装置/部分召唤物无朝向，不输出 facing
                head = "deploy %s at %s" % (who_name, _loc_text(a.get("location")))
        elif act_type == "skill":
            head = "skill %s" % (name or _loc_text(a.get("location")))
        else:
            # 撤退可按干员名，也可按格子（作业未具名时）
            head = "retreat %s" % name if name else \
                "retreat at %s" % _loc_text(a.get("location"))
        answer = head + "\n理由：\n" + "\n".join(
            "%d) %s" % (i + 1, r) for i, r in enumerate(reasons))
        answer += "\n（注：理由由作业时间轴反推 inferred，非作业作者原话）"

        examples.append({
            "question": question,
            "answer": answer,
            "meta": {
                "stage": stage_code,
                "source_job": job.get("title", stage_code),
                "index": idx,
                "action": act_type,
                "action_raw": raw_type,
                "kills": kills,
                "cost": cost,
                "operator": name,
                "location": a.get("location"),
                "direction": a.get("direction"),
                "prts_stage_available": stage_json is not None,
                "prts_operator_available": op_json is not None,
                "evidence": evidence,
            },
        })

        # 用作业动作更新"已部署"前缀状态（只依据作业事实）
        if act_type == "deploy" and name:
            deployed[name] = [a.get("location"), a.get("direction")]
        elif act_type == "retreat":
            if name:
                deployed.pop(name, None)
            else:
                # 按格子撤退：移除落在该坐标的已部署单位
                loc = a.get("location")
                for k in [k for k, v in deployed.items()
                          if loc and isinstance(v, list) and v and v[0] == loc]:
                    deployed.pop(k, None)

    return examples, skipped


# ---------------------------------------------------------------- 落盘
def write_jsonl(examples, out_path):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    return out_path


def group_split_by_stage(examples, eval_ratio=0.1, seed=42):
    # type: (list, float, int) -> tuple
    """按**关卡维度**分组切分，整关样本只进同一侧，杜绝同关数据泄漏到 eval。

    返回 (train_examples, eval_examples, split_meta)。关卡组用固定 seed 洗牌后，
    贪心放入 eval 直到样本数达到约 eval_ratio；关卡样本量不均，实际比例会在目标附近，
    以“无泄漏”为硬约束、比例为软目标。
    """
    groups = {}
    order = []
    for ex in examples:
        stage = str((ex.get("meta") or {}).get("stage") or "_unknown_stage_")
        if stage not in groups:
            groups[stage] = []
            order.append(stage)
        groups[stage].append(ex)
    rng = random.Random(seed)
    rng.shuffle(order)
    target_n = max(1, int(round(len(examples) * eval_ratio)))
    eval_stages, train_stages = [], []
    n_eval = 0
    for stage in order:
        # 已达标即停；未达标则整关放入 eval（即使单关会略超目标也不劈开）
        if n_eval < target_n:
            eval_stages.append(stage)
            n_eval += len(groups[stage])
        else:
            train_stages.append(stage)
    eval_set = [ex for s in eval_stages for ex in groups[s]]
    train_set = [ex for s in train_stages for ex in groups[s]]
    meta = {
        "split": "group_by_stage",
        "seed": seed,
        "n_stages_total": len(order),
        "n_stages_eval": len(eval_stages),
        "n_stages_train": len(train_stages),
        "target_eval_ratio": eval_ratio,
        "actual_eval_ratio": round(len(eval_set) / float(len(examples)), 4) if examples else 0.0,
        "leakage_check": "disjoint" if not (set(eval_stages) & set(train_stages)) else "OVERLAP!",
    }
    return train_set, eval_set, meta


def prepare_jobs(job_paths, out_path, prts_dir=None, eval_ratio=0.0, seed=42,
                 split_by_stage=False, dedup_exact=True):
    # type: (...) -> dict
    # PRTS 索引只构建一次（全量上千作业时避免重复读盘）
    stage_index, op_index = build_prts_index(prts_dir) if prts_dir else ({}, {})
    all_examples = []
    jobs_used = 0
    skipped_total = {}
    for jp in job_paths:
        job = load_maa_job(jp)
        ex, skipped = build_examples(job, stage_index=stage_index,
                                     op_index=op_index)
        all_examples.extend(ex)
        jobs_used += 1
        for k, v in skipped.items():
            skipped_total[k] = skipped_total.get(k, 0) + v

    # 精确去重：question 含关卡标识，跨关不会误并；同关内召唤物“部署→撤回→再部署”
    # 在同状态下产生的完全相同(状态→动作)对属冗余样本，保留首次出现即可。
    n_before_dedup = len(all_examples)
    if dedup_exact:
        seen = set()
        uniq = []
        for ex in all_examples:
            sig = (ex.get("question"), ex.get("answer"))
            if sig in seen:
                continue
            seen.add(sig)
            uniq.append(ex)
        all_examples = uniq
    n_removed_dup = n_before_dedup - len(all_examples)
    write_jsonl(all_examples, out_path)

    written = {"all": out_path, "n_all": len(all_examples), "jobs": jobs_used,
               "skipped": skipped_total, "train": None, "eval": None,
               "n_before_dedup": n_before_dedup, "n_removed_exact_dup": n_removed_dup}
    if eval_ratio and len(all_examples) >= 2 and 0.0 < eval_ratio < 1.0:
        out_dir = os.path.dirname(os.path.abspath(out_path))
        # 切分文件名与 configs/training.yaml 的 sft.train_file/eval_file 对齐
        tp = os.path.join(out_dir, "sft_train.jsonl")
        ep = os.path.join(out_dir, "sft_eval.jsonl")
        if split_by_stage:
            # 按关卡分组：同一关的所有样本只进同一侧，防止数据泄漏到 eval
            train_set, eval_set, split_meta = group_split_by_stage(
                all_examples, eval_ratio=eval_ratio, seed=seed)
            write_jsonl(train_set, tp)
            write_jsonl(eval_set, ep)
            written.update(train=tp, eval=ep, n_train=len(train_set),
                           n_eval=len(eval_set), split=split_meta)
            # 落一份切分清单（与 train/eval 同步，保证可复现、可核对泄漏）
            def _adist(rows):
                c = {}
                for r in rows:
                    a = (r.get("meta") or {}).get("action")
                    c[a] = c.get(a, 0) + 1
                return c
            manifest = {
                "n_all": len(all_examples),
                "n_train": len(train_set),
                "n_eval": len(eval_set),
                "train_ratio": round(len(train_set) / float(len(all_examples)), 4),
                "eval_ratio": split_meta.get("actual_eval_ratio"),
                "split": split_meta.get("split"),
                "seed": seed,
                "n_train_stages": split_meta.get("n_stages_train"),
                "n_eval_stages": split_meta.get("n_stages_eval"),
                "stage_overlap": 0 if split_meta.get("leakage_check") == "disjoint" else -1,
                "leakage_check": split_meta.get("leakage_check"),
                "train_action_dist": _adist(train_set),
                "eval_action_dist": _adist(eval_set),
            }
            mp = os.path.join(out_dir, "sft_split_manifest.json")
            with open(mp, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            written["manifest"] = mp
        else:
            rng = random.Random(seed)
            data = list(all_examples)
            rng.shuffle(data)
            n_eval = max(1, int(round(len(data) * eval_ratio)))
            eval_set, train_set = data[:n_eval], data[n_eval:]
            write_jsonl(train_set, tp)
            write_jsonl(eval_set, ep)
            written.update(train=tp, eval=ep, n_train=len(train_set),
                           n_eval=len(eval_set),
                           split={"split": "random_by_sample", "seed": seed})
    return written


def _gather_jobs(job_input):
    if os.path.isdir(job_input):
        return sorted(glob.glob(os.path.join(job_input, "*.json")))
    return [job_input]


def main(argv=None):
    ap = argparse.ArgumentParser(description="MAA作业+PRTS -> SFT question/answer JSONL")
    ap.add_argument("--job", default=None, help="MAA作业 JSON 文件或目录（默认 config job_dir）")
    ap.add_argument("--prts", default=None, help="PRTS 语料根目录（默认 config prts_dir，可缺失）")
    ap.add_argument("--out", default=None, help="输出 JSONL（默认 config out_dir/default_out_name）")
    ap.add_argument("--split-by-stage", action="store_true",
                    help="train/eval 按关卡维度分组切分（同关不跨集，防泄漏），默认随样本随机切分")
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)

    cfg = load_training_config(args.config).get("data_prep", {})
    job_input = args.job or cfg.get("job_dir", "data/mock")
    prts_dir = args.prts or cfg.get("prts_dir", "data/prts_raw")
    out_path = args.out or os.path.join(cfg.get("out_dir", "data/sft_data"),
                                        cfg.get("default_out_name", "sft_all.jsonl"))
    eval_ratio = 0.0
    if not args.out:
        eval_ratio = float(load_training_config(args.config)
                           .get("sft", {}).get("eval_ratio", 0.0) or 0.0)

    jobs = [p for p in _gather_jobs(job_input)
            if os.path.basename(p).lower().startswith("maa")]
    if not jobs:
        jobs = _gather_jobs(job_input)
    stats = prepare_jobs(jobs, out_path, prts_dir=prts_dir, eval_ratio=eval_ratio,
                         split_by_stage=args.split_by_stage)
    print("[sft_data_prep] 作业 %d 个，产出样本 %d 条 -> %s"
          % (stats["jobs"], stats["n_all"], stats["all"]))
    if stats["skipped"]:
        print("[sft_data_prep] 跳过暂不支持的动作类型：%s" % stats["skipped"])
    if stats.get("train"):
        sm = stats.get("split") or {}
        print("[sft_data_prep] 切分方式=%s train=%d eval=%d（关卡 train=%d/eval=%d，"
              "eval实际占比=%.3f，泄漏检查=%s）"
              % (sm.get("split"), stats["n_train"], stats["n_eval"],
                 sm.get("n_stages_train", -1), sm.get("n_stages_eval", -1),
                 sm.get("actual_eval_ratio", -1), sm.get("leakage_check")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
