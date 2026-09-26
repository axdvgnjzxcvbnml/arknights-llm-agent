# -*- coding: utf-8 -*-
# MAA 作业站（prts.maa.plus，PRTS Plus）专家作业下载器（纯 CPU，I/O 密集）。
#
# 数据合规：
# - 仅访问公开只读接口，顺序请求、默认 1 req/s、不并发、指数退避；遵守站点限流（429/5xx）。
# - 作业为用户上传的公开抄作业 JSON，仅落本地 data/sft_data/（已 .gitignore），**绝不提交 GitHub**。
# - 每份适配件带 _provenance（来源/作业 id/作者/时间/URL），便于署名与溯源。
#
# 接口（2026-09 实测，非臆造）：
#   GET https://prts.maa.plus/copilot/query?type=PRTS&page=N&limit=500
#       -> {status_code, data:{has_next,page,total,data:[{id,type,uploader,upload_time,views,
#          hot_score,rating_level,available,status,content:"<maa-copilot JSON 字符串>"}]}}
#   列表已内联 content，无需再逐 id 调 /copilot/get/<id>，把请求数从"每份作业一个"降到"每页一个"。
#
# 两阶段（避免 4 万条一次性进内存，支持断点续传）：
#   1) enumerate：逐页抓 500 条，整页原样落盘 maa_raw_pages/page_XXX.json（已存在则跳过）。
#   2) curate：离线扫描页文件，按关卡(stage_name)分组，按 rating/views/热度/动作数择优，
#      每关保留 top-K（默认 5），写原始件 maa_jobs_raw/<id>.json 与 SFT 适配件 maa_jobs/maa_*.json。
"""MAA 作业站批量下载 + 转 SFT 适配 schema。"""

import argparse
import glob
import json
import os
import time

import requests

API_BASE = "https://prts.maa.plus"
QUERY_URL = API_BASE + "/copilot/query"
DEFAULT_UA = "arknights-llm-agent/0.1 (+research; respectful sequential 1 req/s)"
MAX_RETRIES = 4

# 原始 maa-copilot 动作/方向 -> 本项目 action 词表（与 action/action_space.py、sft_data_prep 对齐）
ACTION_MAP = {"Deploy": "部署", "SkillUsage": "技能", "Retreat": "撤退"}
SUPPORTED_RAW = set(ACTION_MAP.keys())
DIR_MAP = {"Up": "上", "Down": "下", "Left": "左", "Right": "右"}


# ---------------------------------------------------------------- 网络
def _get_page(session, page, limit, delay, last_ts):
    """取一页；指数退避重试；返回 list[item]。鉴权/封禁类错误抛 RuntimeError 以便上层停下。"""
    params = {"type": "PRTS", "page": page, "limit": limit, "desc": "true"}
    data = None
    for attempt in range(1, MAX_RETRIES + 1):
        elapsed = time.time() - last_ts[0]
        if elapsed < delay:
            time.sleep(delay - elapsed)
        last_ts[0] = time.time()
        try:
            resp = session.get(QUERY_URL, params=params, timeout=40)
        except requests.RequestException as exc:
            print("[maa] 第 %d 页网络异常: %s，重试(%d/%d)" % (page, exc, attempt, MAX_RETRIES))
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 200:
            data = resp.json()
            break
        if resp.status_code in (429, 500, 502, 503, 504):
            wait = 2 ** attempt
            print("[maa] 第 %d 页状态 %s，%ds 后重试(%d/%d)" % (page, resp.status_code, wait, attempt, MAX_RETRIES))
            time.sleep(wait)
            continue
        # 401/403/其它：可能是鉴权或反爬，按约定停下而不是硬冲
        raise RuntimeError("作业站返回非限流错误 HTTP %s：停止下载（疑似鉴权/反爬），请人工确认" % resp.status_code)
    if data is None:
        raise RuntimeError("第 %d 页重试 %d 次后仍失败" % (page, MAX_RETRIES))
    if data.get("status_code") != 200:
        raise RuntimeError("作业站 status_code=%s message=%s" % (data.get("status_code"), data.get("message")))
    return data["data"]


def enumerate_jobs(out_root, limit=500, delay=1.0, max_pages=None):
    pages_dir = os.path.join(out_root, "maa_raw_pages")
    os.makedirs(pages_dir, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": DEFAULT_UA})
    last_ts = [0.0]
    page = 1
    total = None
    fetched = skipped_pages = 0
    while True:
        if max_pages is not None and page > max_pages:
            print("[maa] 达到 --max-pages=%d，停止枚举" % max_pages)
            break
        pf = os.path.join(pages_dir, "page_%03d.json" % page)
        if os.path.exists(pf) and os.path.getsize(pf) > 0:
            try:
                with open(pf, encoding="utf-8") as f:
                    payload = json.load(f)
                skipped_pages += 1
            except (ValueError, OSError) as exc:
                print("[maa] 分页缓存损坏，删除后重抓：%s（%s）" % (pf, exc))
                payload = None
            if payload is None:
                os.remove(pf)
        else:
            payload = _get_page(session, page, limit, delay, last_ts)
            with open(pf, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            fetched += 1
        if total is None:
            total = payload.get("total")
            print("[maa] 作业站 PRTS 作业总数 total=%s（分页大小 %d）" % (total, limit))
        items = payload.get("data", [])
        print("[maa] 第 %3d 页：%d 条（新抓 %d / 复用 %d 页）" % (page, len(items), fetched, skipped_pages))
        if not payload.get("has_next") or not items:
            break
        page += 1
    return {"total": total, "pages": page, "fetched": fetched, "reused": skipped_pages}


# ---------------------------------------------------------------- 适配
def _safe(s):
    return str(s).replace("/", "_").replace(":", "_").replace("\\", "_")


def adapt_item(item, content):
    """把站点原始 maa-copilot content 转成 sft_data_prep 期望的 {stage_name,title,details,...}。

    无法用于 SFT（缺 stage_name / 无受支持动作）时返回 None。
    """
    stage = content.get("stage_name")
    if not stage:
        return None
    raw_actions = content.get("actions") or []
    adapted = []
    skip_types = {}
    for a in raw_actions:
        rt = a.get("type")
        if rt not in SUPPORTED_RAW:
            skip_types[rt] = skip_types.get(rt, 0) + 1
            continue
        aa = {
            "type": ACTION_MAP[rt],
            "name": a.get("name"),
            "kills": a.get("kills", 0),
            "cost_changes": a.get("cost_changes"),
        }
        if "location" in a:
            aa["location"] = a.get("location")
        d = a.get("direction")
        if d in DIR_MAP:
            aa["direction"] = DIR_MAP[d]
        if "skill_usage" in a:
            aa["skill_usage"] = a.get("skill_usage")
        adapted.append({k: v for k, v in aa.items() if v is not None})
    if not adapted:
        return None
    doc = content.get("doc") or {}
    opers = []
    for o in content.get("opers") or []:
        if o.get("name"):
            oo = {"name": o["name"]}
            for k in ("skill", "skill_usage"):
                if k in o:
                    oo[k] = o[k]
            opers.append(oo)
    job = {
        "minimum_required": content.get("minimum_required"),
        "stage_name": stage,
        "title": doc.get("title") or stage,
        "details": {
            "cost_limit": content.get("cost_limit"),
            "opers": opers,
            "actions": adapted,
        },
        "_provenance": {
            "source": "prts.maa.plus",
            "copilot_id": item.get("id"),
            "uploader": item.get("uploader"),
            "upload_time": item.get("upload_time"),
            "views": item.get("views"),
            "rating_level": item.get("rating_level"),
            "url": "%s/copilot/get/%s" % (API_BASE, item.get("id")),
            "adapted_action_types": skip_types,
        },
        "_note": "本文件由公开 MAA 作业站作业(maa-copilot)适配而来，仅本地用于 SFT 数据准备，禁止提交。",
    }
    return job


def _get_job(session, cid, delay, last_ts):
    """取单份作业全文（列表接口会裁掉 actions，必须逐 id get）。"""
    url = "%s/copilot/get/%s" % (API_BASE, cid)
    for attempt in range(1, MAX_RETRIES + 1):
        elapsed = time.time() - last_ts[0]
        if elapsed < delay:
            time.sleep(delay - elapsed)
        last_ts[0] = time.time()
        try:
            resp = session.get(url, timeout=40)
        except requests.RequestException as exc:
            print("[maa] get %s 网络异常: %s，重试(%d/%d)" % (cid, exc, attempt, MAX_RETRIES))
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 200:
            data = resp.json()
            break
        if resp.status_code in (429, 500, 502, 503, 504):
            wait = 2 ** attempt
            print("[maa] get %s 状态 %s，%ds 后重试(%d/%d)" % (cid, resp.status_code, wait, attempt, MAX_RETRIES))
            time.sleep(wait)
            continue
        raise RuntimeError("get %s 返回非限流错误 HTTP %s：停止（疑似鉴权/反爬）" % (cid, resp.status_code))
    else:
        raise RuntimeError("get %s 重试耗尽" % cid)
    if data.get("status_code") != 200 or not data.get("data"):
        return None  # available=false 等情况
    return data["data"]


def _list_quality(item):
    # 列表元数据可用于排序（actions 已被裁，无法据此排序）
    return (
        int(item.get("not_enough_rating") is False),   # 评分样本足够者优先
        int(item.get("rating_level") or 0),
        int(item.get("views") or 0),
        float(item.get("hot_score") or 0.0),
    )


def curate(out_root, per_stage=5, keep_all=False, buffer_extra=4, delay=1.0):
    """离线选候选 -> 顺序 get 全文（resume）-> 适配；每关保留至多 per_stage 份有效作业。"""
    pages_dir = os.path.join(out_root, "maa_raw_pages")
    raw_dir = os.path.join(out_root, "maa_jobs_raw")
    job_dir = os.path.join(out_root, "maa_jobs")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(job_dir, exist_ok=True)

    # ---- 1) 从索引页按关卡聚合候选（仅含 stage_name 的公开 PRTS 作业）----
    seen = 0
    candidates = {}   # stage -> [item,...]
    for pf in sorted(glob.glob(os.path.join(pages_dir, "page_*.json"))):
        try:
            with open(pf, encoding="utf-8") as f:
                payload = json.load(f)
        except (ValueError, OSError) as exc:
            print("[maa] 跳过损坏的索引页：%s（%s）" % (pf, exc))
            continue
        for item in payload.get("data", []):
            if item.get("type") != "PRTS" or not item.get("available", True):
                continue
            try:
                head = json.loads(item.get("content") or "{}")
            except (ValueError, TypeError):
                continue
            stage = head.get("stage_name")
            if not stage:
                continue
            seen += 1
            candidates.setdefault(stage, []).append(item)

    plan = {}        # cid -> item，需要 get 全文的候选
    for stage, items in candidates.items():
        items.sort(key=_list_quality, reverse=True)
        chosen = items if keep_all else items[:per_stage + buffer_extra]
        for it in chosen:
            plan[it["id"]] = it

    # ---- 2) 顺序取全文（已存在则跳过，断点续传）----
    todo = [cid for cid in plan if not os.path.exists(os.path.join(raw_dir, "%s.json" % cid))]
    print("[maa] 索引中含关卡的作业 %d，覆盖 %d 关；候选 %d 份，需新 get %d 份（约 %d 秒@1req/s）"
          % (seen, len(candidates), len(plan), len(todo), int(len(todo) * delay)))
    session = requests.Session()
    session.headers.update({"User-Agent": DEFAULT_UA})
    last_ts = [0.0]
    got = failed = 0
    for n, cid in enumerate(todo, 1):
        try:
            full = _get_job(session, cid, delay, last_ts)
        except RuntimeError as exc:
            print("[maa] 停止：%s" % exc)
            break
        if full is None:
            failed += 1
            continue
        try:
            content = json.loads(full.get("content") or "{}")
        except (ValueError, TypeError):
            failed += 1
            continue
        with open(os.path.join(raw_dir, "%s.json" % cid), "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False)
        got += 1
        if n % 50 == 0:
            print("[maa] 已 get %d/%d（成功 %d）" % (n, len(todo), got))

    # ---- 3) 适配全文，按关保留前 K 份"含受支持动作"的有效作业 ----
    id_item = {it["id"]: it for it in plan.values()}
    per_stage_valid = {}
    written_raw = written_adapted = 0
    for stage, items in candidates.items():
        items.sort(key=_list_quality, reverse=True)
        kept = 0
        for it in (items if keep_all else items):
            if (not keep_all) and kept >= per_stage:
                break
            cid = it["id"]
            rp = os.path.join(raw_dir, "%s.json" % cid)
            if not os.path.exists(rp):
                continue
            try:
                with open(rp, encoding="utf-8") as f:
                    content = json.load(f)
            except (ValueError, OSError) as exc:
                print("[maa] 跳过损坏的作业原始件：%s（%s）" % (rp, exc))
                continue
            job = adapt_item(it, content)
            if job is None:
                continue  # 全文也没有受支持动作（纯加速/视角宏等）
            written_raw += 0  # 原始件在 get 时已落盘
            fn = "maa_%s_%s.json" % (cid, _safe(stage))
            with open(os.path.join(job_dir, fn), "w", encoding="utf-8") as f:
                json.dump(job, f, ensure_ascii=False, indent=2)
            written_adapted += 1
            kept += 1
        per_stage_valid[stage] = kept
    raw_on_disk = len(glob.glob(os.path.join(raw_dir, "*.json")))
    stats = {
        "index_jobs_with_stage": seen,
        "unique_stages": len(candidates),
        "candidate_jobs": len(plan),
        "new_fetched_full": got,
        "fetch_failed_or_empty": failed,
        "raw_full_on_disk": raw_on_disk,
        "adapted_for_sft": written_adapted,
        "stages_with_valid_job": sum(1 for v in per_stage_valid.values() if v > 0),
        "per_stage_cap": None if keep_all else per_stage,
        "raw_dir": raw_dir,
        "adapted_dir": job_dir,
    }
    with open(os.path.join(out_root, "maa_download_stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    return stats, per_stage_valid


def main(argv=None):
    ap = argparse.ArgumentParser(description="下载 MAA 作业站作业并适配为 SFT 输入")
    ap.add_argument("--out-root", default="data/sft_data")
    ap.add_argument("--page-limit", type=int, default=500)
    ap.add_argument("--delay", type=float, default=1.0, help="每页请求间隔秒（默认 1.0，勿调小压站）")
    ap.add_argument("--max-pages", type=int, default=None, help="只抓前 N 页（联调用）")
    ap.add_argument("--per-stage", type=int, default=5, help="每个关卡保留 top-K 高质量作业（默认5）")
    ap.add_argument("--buffer", type=int, default=4, help="每关多取 N 份候选以应对全文无有效动作（默认4）")
    ap.add_argument("--keep-all", action="store_true", help="保留全部可用作业（不按关卡裁剪）")
    ap.add_argument("--enumerate-only", action="store_true", help="只抓索引页，不逐 id 取全文")
    ap.add_argument("--curate-only", action="store_true", help="不联网抓索引，仅用已落盘索引取全文并适配")
    args = ap.parse_args(argv)

    if not args.curate_only:
        est = enumerate_jobs(args.out_root, limit=args.page_limit, delay=args.delay,
                             max_pages=args.max_pages)
        print("[maa] 枚举完成：%s" % est)
    if args.enumerate_only:
        return 0
    stats, per_stage = curate(args.out_root, per_stage=args.per_stage,
                              keep_all=args.keep_all, buffer_extra=args.buffer,
                              delay=args.delay)
    print("[maa] 择优完成：")
    for k, v in stats.items():
        if not k.endswith("_dir"):
            print("    %-28s %s" % (k, v))
    print("[maa] 适配件目录：%s（用 python -m training.sft_data_prep --job %s 转 SFT）"
          % (stats["adapted_dir"], stats["adapted_dir"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
