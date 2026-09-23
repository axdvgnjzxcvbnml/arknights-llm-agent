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

from .config import load_training_config

__all__ = [
    "load_maa_job", "build_prts_index", "build_examples", "write_jsonl",
    "prepare_jobs", "SUPPORTED_ACTIONS",
]

# MAA 动作类型 -> 本项目 action 词表（与 action/action_space.py 对齐）
SUPPORTED_ACTIONS = {"部署": "deploy", "技能": "skill", "撤退": "retreat"}
DIRECTIONS = ("上", "下", "左", "右")


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
            d = json.load(open(p, encoding="utf-8"))
        except (ValueError, OSError):
            continue
        code = d.get("code")
        if code:
            stages[str(code)] = d
    for p in glob.glob(os.path.join(prts_dir, "operators", "*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (ValueError, OSError):
            continue
        name = d.get("name")
        if name:
            ops[str(name)] = d
    return stages, ops


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
    return name + (("（%s）" % "/".join(tags)) if tags else "")


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
        sname = normal.get("name") or stage_json.get("name") or ""
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
        L.append("[已部署] " + "；".join("%s%s朝%s" % (n, _loc_text(v[0]), v[1])
                                        for n, v in deployed.items()))
    else:
        L.append("[已部署] 无")
    L.append("[任务] 给出下一步动作与理由（动作词表：deploy/skill/retreat/wait）。")
    return "\n".join(L)


def _rationale(act_type, a, op_json, stage_json, deployed, prts_ok):
    # type: (...) -> tuple
    """返回 (理由列表, evidence_dict)。理由是推断；属性/敌情是事实。"""
    name = a.get("name", "?")
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

    who = "%s（%s/%s）" % (name, cls, branch) if cls else name
    if act_type == "deploy":
        reasons.append("%s %s 于%s朝%s——%s（动作来自作业时间轴）" % (
            "部署", who, _loc_text(a.get("location")), a.get("direction", "?"), trig))
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
        else:
            reasons.append("按作业要求在此节点补齐阵容")
    elif act_type == "skill":
        skill_names = _operator_skill_names(op_json) if op_json else []
        skill_hint = ("技能候选：%s；" % "、".join(skill_names)) if skill_names else ""
        reasons.append("开启 %s 的技能——%s（动作来自作业时间轴）" % (name, trig))
        reasons.append(skill_hint + "波次压力上升时用技能提升爆发/续航，应对当前接敌")
    elif act_type == "retreat":
        reasons.append("撤退 %s——%s（动作来自作业时间轴）" % (name, trig))
        reasons.append("释放部署位/部分费用并进入再部署循环，为后续关键节点腾挪资源")
    return reasons, evidence


# ---------------------------------------------------------------- 主构造
def build_examples(job, prts_dir=None, stage_json=None, op_index=None):
    # type: (dict, str, object, object) -> tuple
    if prts_dir is not None and stage_json is None:
        stages, ops = build_prts_index(prts_dir)
    else:
        stages, ops = {}, {}
    if op_index is not None:
        ops = op_index
    stage_code = str(job.get("stage_name"))
    if stage_json is None:
        stage_json = stages.get(stage_code)
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

        question = _state_question(stage_code, stage_json, kills, cost,
                                   deployed, prts_ok)
        reasons, evidence = _rationale(act_type, a, op_json, stage_json,
                                       deployed, prts_ok)
        # 答案：先一句动作，再列理由
        if act_type == "deploy":
            head = "deploy %s at %s facing %s" % (
                name, _loc_text(a.get("location")), a.get("direction", "?"))
        elif act_type == "skill":
            head = "skill %s" % name
        else:
            head = "retreat %s" % name
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
        elif act_type == "retreat" and name:
            deployed.pop(name, None)

    return examples, skipped


# ---------------------------------------------------------------- 落盘
def write_jsonl(examples, out_path):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    return out_path


def prepare_jobs(job_paths, out_path, prts_dir=None, eval_ratio=0.0, seed=42):
    # type: (...) -> dict
    all_examples = []
    jobs_used = 0
    skipped_total = {}
    for jp in job_paths:
        job = load_maa_job(jp)
        ex, skipped = build_examples(job, prts_dir=prts_dir)
        all_examples.extend(ex)
        jobs_used += 1
        for k, v in skipped.items():
            skipped_total[k] = skipped_total.get(k, 0) + v
    write_jsonl(all_examples, out_path)

    written = {"all": out_path, "n_all": len(all_examples), "jobs": jobs_used,
               "skipped": skipped_total, "train": None, "eval": None}
    if eval_ratio and len(all_examples) >= 2 and 0.0 < eval_ratio < 1.0:
        rng = random.Random(seed)
        data = list(all_examples)
        rng.shuffle(data)
        n_eval = max(1, int(round(len(data) * eval_ratio)))
        eval_set, train_set = data[:n_eval], data[n_eval:]
        out_dir = os.path.dirname(os.path.abspath(out_path))
        # 切分文件名与 configs/training.yaml 的 sft.train_file/eval_file 对齐
        tp = os.path.join(out_dir, "sft_train.jsonl")
        ep = os.path.join(out_dir, "sft_eval.jsonl")
        write_jsonl(train_set, tp)
        write_jsonl(eval_set, ep)
        written.update(train=tp, eval=ep, n_train=len(train_set), n_eval=len(eval_set))
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
    stats = prepare_jobs(jobs, out_path, prts_dir=prts_dir, eval_ratio=eval_ratio)
    print("[sft_data_prep] 作业 %d 个，产出样本 %d 条 -> %s"
          % (stats["jobs"], stats["n_all"], stats["all"]))
    if stats["skipped"]:
        print("[sft_data_prep] 跳过暂不支持的动作类型：%s" % stats["skipped"])
    if stats.get("train"):
        print("[sft_data_prep] 切分 train=%d eval=%d"
              % (stats["n_train"], stats["n_eval"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
