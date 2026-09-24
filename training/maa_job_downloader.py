"""MAA 作业下载器（prts.maa.plus）。

从作业站批量下载关卡作业（每关最优 1 份），存为 JSONL 到指定目录。
尊重站方限速：默认 1.2s 间隔，429 退避；断点续传（已下载关卡跳过）。
"""

import argparse
import json
import os
import time

import requests

__all__ = ["download_jobs", "main"]

API = "https://prts.maa.plus/api/v1/stages/"
DEFAULT_OUT = os.path.join("data", "sft_data", "maa_jobs")


def _job_url(stage_id):
    return API + str(stage_id)


def _headers():
    return {"User-Agent": "arknights-llm-agent/0.1 (SFT data prep)"}


def download_jobs(stage_ids, out_dir=None, delay=1.2, force=False):
    # type: (list, str, float, bool) -> dict
    """下载指定关卡作业；已存在且非 force 时跳过。返回 {stage_id: bool}。"""
    out_dir = out_dir or DEFAULT_OUT
    os.makedirs(out_dir, exist_ok=True)
    result = {}
    for sid in stage_ids:
        fp = os.path.join(out_dir, "%s.jsonl" % sid)
        if os.path.isfile(fp) and not force:
            result[sid] = False
            continue
        try:
            r = requests.get(_job_url(sid), headers=_headers(), timeout=30)
            r.raise_for_status()
            data = r.json()
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                time.sleep(delay * 5)
            print("[warn] %s 下载失败: %s" % (sid, e))
            result[sid] = False
            continue
        except Exception as e:
            print("[warn] %s 下载失败: %s" % (sid, e))
            result[sid] = False
            continue
        items = data.get("data", []) or []
        if not items:
            result[sid] = False
            continue
        best = items[0]  # 接口按热度/质量排序，取第 1 份
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"stage_id": sid, "job": best}, f, ensure_ascii=False)
            f.write("\n")
        result[sid] = True
        time.sleep(delay)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="下载 MAA 作业（prts.maa.plus）")
    ap.add_argument("--stages", required=True, help="关卡 id 文件（每行一个）或逗号分隔列表")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--delay", type=float, default=1.2)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    if os.path.isfile(args.stages):
        with open(args.stages, "r", encoding="utf-8") as f:
            stage_ids = [ln.strip() for ln in f if ln.strip()]
    else:
        stage_ids = [s.strip() for s in args.stages.split(",") if s.strip()]
    result = download_jobs(stage_ids, out_dir=args.out, delay=args.delay, force=args.force)
    ok = sum(1 for v in result.values() if v)
    print("下载完成：%d/%d -> %s" % (ok, len(result), args.out))
    return 0 if ok == len(result) else 1


if __name__ == "__main__":
    raise SystemExit(main())
