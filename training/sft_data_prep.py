"""SFT 数据准备（CPU 真实实现）。

把 MAA 作业（data/sft_data/maa_jobs/<stage>.jsonl 的时间轴动作）与 PRTS 结构化
语料（data/prts_raw）反推成 (question, answer) 训练样本：

- question：从"关卡 + 已部署状态 + 当前费用/击杀/时间"构造；
- answer：动作（deploy/skill/retreat）+ 理由（evidence 分级）。

证据分层：
- 动作 = fact:maa_job（来自作业时间轴）；命中 PRTS 的关卡敌情/干员职业另标 fact:prts。
- 理由 = inferred:timeline_reconstructed（反推，非作业作者原话）。

过滤：
- 泛称/灵活位占位（职业黑话/练度要求）不入训（is_generic_operator）；
- 未识别动作（上传者未命名）跳过；
- 完全重复的 (状态→动作) 对精确去重（撤退→再部署场景保留首次）。

切分：按关卡分组（同关只进一侧），train/eval 无同关泄漏。
"""

import argparse
import glob
import json
import os
import random
import re

__all__ = ["is_generic_operator", "prepare_sft", "main"]

DEFAULT_OUT = os.path.join("data", "sft_data")
GENERIC_EXACT = {
    # 职业/分支/黑话精确词（高精度白名单，宁漏勿错）+ MAA 空槽哨兵
    "输出", "奶盾", "单奶", "速狙", "投锋", "快活", "工具人", "坦克", "大奶盾",
    "铁卫", "伏击客", "守护者", "强攻手", "速射手", "重剑手", "远卫", "法师",
    "术师", "医疗", "狙击", "重装", "先锋", "近卫", "辅助", "特种",
    "Unknown_EndsEmpty",
}

# 结构判据（零误伤：真实干员/召唤物/装置名不会命中）
RE_LIANDU = re.compile(r"【[^】]+】|练度|精[一二三]|满级|及以上|专三")
RE_CLASS_BRANCH = re.compile(r"^(?:八大职业|铁卫|医疗|狙击|重装|先锋|近卫|辅助|特种)-[\u4e00-\u9fa5]{2,6}$")
RE_CLASS_NUM = re.compile(r"^(?:职业|奶|盾)[\d一二三四五六七八九十百]+$")
RE_SHORT_REQ = re.compile(r"^.{1,8}：.*(?:精[一二三]|满级|练度|级及以上)")


def is_generic_operator(name):
    # type: (str) -> bool
    """判断动作对象是否为"需求型灵活位/泛称"（不可执行），应剔除。"""
    if not name:
        return True
    if name in GENERIC_EXACT:
        return True
    if RE_LIANDU.search(name):
        return True
    if RE_CLASS_BRANCH.match(name):
        return True
    if RE_CLASS_NUM.match(name):
        return True
    if RE_SHORT_REQ.match(name):
        return True
    return False


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_prts_index(prts_dir):
    # type: (str) -> dict
    """加载 PRTS 语料索引：{页面标题: {kind, name, ...}}，用于富化。"""
    idx = {}
    if not prts_dir:
        return idx
    base = os.path.join(prts_dir, "operators")
    for p in glob.glob(os.path.join(base, "*.json")):
        try:
            d = _load_json(p)
        except ValueError:
            continue
        page = os.path.splitext(os.path.basename(p))[0]
        idx[page] = {"kind": "operator", "name": d.get("name", page),
                     "class": d.get("class", ""), "star": d.get("rarity", "")}
    base = os.path.join(prts_dir, "stages")
    for p in glob.glob(os.path.join(base, "*.json")):
        try:
            d = _load_json(p)
        except ValueError:
            continue
        code = d.get("code")
        if not code:
            continue
        idx[str(code)] = {"kind": "stage", "name": d.get("name", code),
                          "enemies": [(e.get("display") or e.get("name"), e.get("count"))
                                       for e in (d.get("enemies") or [])]}
    return idx


def _state_question(stage_id, prts_idx, deployed, cost, kills, elapsed):
    # type: (str, dict, list, int, int, float) -> str
    """构造状态问题。关卡名优先顶层 name（避免信息卡 UI 文案污染，见 troubleshooting）。"""
    st = prts_idx.get(str(stage_id)) or {}
    stage_name = st.get("name") or stage_id
    deployed_txt = "、".join(sorted(d for d in deployed)) if deployed else "无"
    return ("[关卡 %s] 当前已部署干员：%s；费用 %d，已击杀 %d，用时 %.1fs。请给出下一步行动。"
            % (stage_name, deployed_txt, cost, kills, elapsed))


def _answer_for(action, prts_idx, stage_id):
    # type: (dict, dict, str) -> str
    """动作 -> answer 文本（动作 fact:maa_job + 理由 inferred 反推 + PRTS 富化）。"""
    op = action.get("name", "")
    atype = action.get("type", "")
    if atype == "deploy":
        coord = action.get("coords") or []
        facing = action.get("facing")
        pos = "(%s,%s)" % (coord[0], coord[1]) if len(coord) >= 2 else "?"
        face_txt = ("朝向%s" % facing) if facing else ""
        base = "deploy %s at %s %s。" % (op, pos, face_txt)
    elif atype == "skill":
        base = "skill %s。" % op
    elif atype == "retreat":
        base = "retreat %s。" % op
    else:
        base = "wait。"
    reason = "理由：inferred:timeline_reconstructed（根据 MAA 作业时间轴反推）"
    st = prts_idx.get(str(stage_id)) or {}
    if st.get("kind") == "stage" and st.get("enemies"):
        names = [n for n, _c in st["enemies"] if n]
        if names:
            reason += "；本关敌情（fact:prts）：%s" % "、".join(names[:6])
    return base + reason


def _deployed_from(actions, up_to):
    # type: (list, int) -> list
    """前缀已部署状态：up_to 步（不含）之前 deploy 且未 retreat 的干员。"""
    out = []
    for a in actions[:up_to]:
        nm = a.get("name")
        if not nm:
            continue
        if a.get("type") == "deploy":
            out.append(nm)
        elif a.get("type") == "retreat" and nm in out:
            out.remove(nm)
    return out


def _iter_actions(job):
    """从 MAA 作业 JSON 提取动作时间轴（(elapsed, action) 列表）。"""
    out = []
    for grp in job.get("actions") or []:
        t = float(grp.get("time", 0) or 0)
        for a in grp.get("details") or []:
            out.append((t, a))
    out.sort(key=lambda x: x[0])
    return out


def prepare_sft(job_dir, prts_dir=None, out_dir=None, split=True, seed=42,
                force=False):
    # type: (str, str, str, bool, int, bool) -> dict
    """准备 SFT 数据集。返回 {train, eval, dropped, stats}。"""
    out_dir = out_dir or DEFAULT_OUT
    os.makedirs(out_dir, exist_ok=True)
    prts_idx = _load_prts_index(prts_dir)
    samples = []  # 每项 (stage_id, question, answer, meta)
    dropped = {"generic": 0, "unknown": 0, "duplicate": 0}
    seen = set()

    for p in sorted(glob.glob(os.path.join(job_dir, "*.jsonl"))):
        stage_id = os.path.splitext(os.path.basename(p))[0]
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                job = obj.get("job") or {}
                timeline = _iter_actions(job)
                kills = 0
                cost = 0
                for i, (t, a) in enumerate(timeline):
                    nm = a.get("name") or a.get("name_cn") or ""
                    atype = a.get("type", "")
                    if atype not in ("deploy", "skill", "retreat"):
                        dropped["unknown"] += 1
                        continue
                    if atype == "deploy":
                        if is_generic_operator(nm):
                            dropped["generic"] += 1
                            continue
                        cost += 1
                    elif atype == "retreat":
                        if is_generic_operator(nm):
                            dropped["generic"] += 1
                            continue
                        cost -= 1
                    deployed = _deployed_from([x[1] for x in timeline], i)
                    q = _state_question(stage_id, prts_idx, deployed, cost, kills, t)
                    a = _answer_for(a, prts_idx, stage_id)
                    meta = {"stage": stage_id, "action": atype,
                            "operator": nm,
                            "coords": a.get("coords") if atype == "deploy" else None,
                            "facing": a.get("facing") if atype == "deploy" else None,
                            "kills": kills, "cost": cost, "elapsed": round(t, 2)}
                    key = (q, a)
                    if key in seen:
                        dropped["duplicate"] += 1
                        continue
                    seen.add(key)
                    samples.append((stage_id, q, a, meta))

    # 按关卡分组切分
    by_stage = {}
    for s in samples:
        by_stage.setdefault(s[0], []).append(s)
    stages = sorted(by_stage)
    rng = random.Random(seed)
    rng.shuffle(stages)
    n_eval = max(1, int(len(stages) * 0.10))
    eval_stages = set(stages[:n_eval])

    def _write(path, items):
        with open(path, "w", encoding="utf-8") as f:
            for _sid, q, a, m in items:
                f.write(json.dumps({"question": q, "answer": a, "meta": m},
                                   ensure_ascii=False) + "\n")

    train_items = [s for s in samples if s[0] not in eval_stages]
    eval_items = [s for s in samples if s[0] in eval_stages]
    _write(os.path.join(out_dir, "sft_train.jsonl"), train_items)
    _write(os.path.join(out_dir, "sft_eval.jsonl"), eval_items)
    manifest = {"seed": seed, "train_stages": len(stages) - n_eval,
                "eval_stages": n_eval, "train": len(train_items),
                "eval": len(eval_items), "dropped": dropped}
    with open(os.path.join(out_dir, "sft_split_manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description="SFT 数据准备（MAA 作业 -> JSONL）")
    ap.add_argument("--job", default=os.path.join("data", "sft_data", "maa_jobs"))
    ap.add_argument("--prts", default="data/prts_raw")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--split-by-stage", action="store_true", dest="split")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    manifest = prepare_sft(job_dir=args.job, prts_dir=args.prts,
                           out_dir=args.out, split=args.split, force=args.force)
    print("train=%d eval=%d dropped=%s -> %s" % (manifest["train"],
          manifest["eval"], manifest["dropped"], args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
