"""PRTS Wiki 批量爬取入口。

分类结构（2026-09 经 api.php 实测确认）：
- operator -> Category:干员   （460 页，含异格形态如"阿米娅(近卫)"）
- enemy    -> Category:敌人   （500+ 页，需 cmcontinue 翻页）
- stage    -> Category:主线关卡（Category:关卡 不存在；标题格式"3-8 黄昏"）

能力：
- 通过 MediaWiki API categorymembers 翻页获取标题列表；
- 逐个调用 PrtsCrawler 抓取并解析，落盘 data/prts_raw/{operators,enemies,stages}/；
- 限速 1 请求/秒（API 与页面请求均限速），429/5xx 指数退避重试；
- 断点续爬：目标 JSON 已存在且非空则跳过（--force 强制重爬）。

CLI 用法：
    python -m knowledge.crawler.batch_crawl --type operator --limit 50
    python -m knowledge.crawler.batch_crawl --type enemy    --limit 50
    python -m knowledge.crawler.batch_crawl --type stage    --limit 20
"""

import argparse
import json
import os
import time

import requests

from .prts_crawler import DEFAULT_DELAY, DEFAULT_UA, MAX_RETRIES, PrtsCrawler

__all__ = ["CATEGORY_MAP", "list_category_titles", "batch_crawl"]

# 爬取类型 -> (PRTS 分类名, PrtsCrawler 方法名, 输出子目录)
CATEGORY_MAP = {
    "operator": ("干员", "crawl_operator", "operators"),
    "enemy": ("敌人", "crawl_enemy", "enemies"),
    "stage": ("主线关卡", "crawl_stage", "stages"),
}

API_URL = "https://prts.wiki/api.php"


def _safe_name(title):
    # type: (str) -> str
    """与 PrtsCrawler._save_json 相同的文件名安全化规则。"""
    return title.replace("/", "_").replace(":", "_")


def list_category_titles(category, limit=None, delay=DEFAULT_DELAY, user_agent=DEFAULT_UA):
    # type: (str, int, float, str) -> list
    """通过 categorymembers API 获取分类下全部页面标题（自动 cmcontinue 翻页）。

    :param category: PRTS 分类名（不带"Category:"前缀），如"干员"
    :param limit: 最多返回多少条；None 表示取全部分类成员
    """
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    titles = []
    cmcontinue = None
    last_ts = [0.0]

    def _wait():
        elapsed = time.time() - last_ts[0]
        if elapsed < delay:
            time.sleep(delay - elapsed)
        last_ts[0] = time.time()

    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": "Category:" + category,
            "cmnamespace": "0",
            "cmlimit": "500",
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue

        data = None
        for attempt in range(1, MAX_RETRIES + 1):
            _wait()
            try:
                resp = session.get(API_URL, params=params, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    break
                if resp.status_code in (429, 500, 502, 503, 504):
                    time.sleep(2 ** attempt)
                    continue
                print("[batch] 分类列表请求异常状态 %s，终止" % resp.status_code)
                return titles
            except (requests.RequestException, ValueError) as exc:
                print("[batch] 分类列表请求失败: %s，重试(%d/%d)" % (exc, attempt, MAX_RETRIES))
                time.sleep(2 ** attempt)
        if data is None:
            print("[batch] 分类 %s 列表获取失败（重试耗尽），已获取 %d 条" % (category, len(titles)))
            return titles

        members = data.get("query", {}).get("categorymembers", [])
        for m in members:
            if m.get("ns") == 0:
                titles.append(m["title"])
                if limit is not None and len(titles) >= limit:
                    return titles

        cont = data.get("continue", {})
        cmcontinue = cont.get("cmcontinue")
        if not cmcontinue:
            break
    return titles


def batch_crawl(kind, limit=50, output_dir="data/prts_raw", delay=DEFAULT_DELAY, force=False):
    # type: (str, int, str, float, bool) -> dict
    """批量爬取某一类型页面。

    :return: 统计 dict {total, crawled, skipped, failed, failed_titles}
    """
    if kind not in CATEGORY_MAP:
        raise ValueError("未知类型 %r，可选：%s" % (kind, sorted(CATEGORY_MAP.keys())))
    category, crawl_method, subdir = CATEGORY_MAP[kind]
    json_dir = os.path.join(output_dir, subdir)
    os.makedirs(json_dir, exist_ok=True)

    print("[batch] 获取 Category:%s 的页面标题列表 ..." % category)
    titles = list_category_titles(category, limit=limit, delay=delay)
    print("[batch] 共 %d 个待处理页面（limit=%s）" % (len(titles), limit))

    crawler = PrtsCrawler(output_dir=output_dir, delay=delay)
    crawl_fn = getattr(crawler, crawl_method)

    stats = {"total": len(titles), "crawled": 0, "skipped": 0, "failed": 0, "failed_titles": []}
    for i, title in enumerate(titles, 1):
        json_path = os.path.join(json_dir, _safe_name(title) + ".json")
        if not force and os.path.exists(json_path) and os.path.getsize(json_path) > 0:
            stats["skipped"] += 1
            print("[batch] (%d/%d) 跳过（已存在）: %s" % (i, len(titles), title))
            continue
        try:
            data = crawl_fn(title)
        except Exception as exc:  # 单页异常不中断整批
            print("[batch] (%d/%d) 异常: %s -> %s" % (i, len(titles), title, exc))
            stats["failed"] += 1
            stats["failed_titles"].append(title)
            continue
        if not data:
            stats["failed"] += 1
            stats["failed_titles"].append(title)
            print("[batch] (%d/%d) 失败: %s" % (i, len(titles), title))
        else:
            stats["crawled"] += 1
            print("[batch] (%d/%d) 完成: %s" % (i, len(titles), title))

    print("[batch] %s 结束：成功 %d，跳过 %d，失败 %d（共 %d）"
          % (kind, stats["crawled"], stats["skipped"], stats["failed"], stats["total"]))
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description="PRTS Wiki 批量爬取")
    parser.add_argument("--type", required=True, choices=sorted(CATEGORY_MAP.keys()),
                        help="爬取类型：operator/enemy/stage")
    parser.add_argument("--limit", type=int, default=50, help="最多爬取页面数（默认 50）")
    parser.add_argument("--output-dir", default="data/prts_raw", help="输出目录")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="请求间隔秒数（默认 1.0）")
    parser.add_argument("--force", action="store_true", help="已存在也强制重爬")
    args = parser.parse_args(argv)

    stats = batch_crawl(args.type, limit=args.limit, output_dir=args.output_dir,
                        delay=args.delay, force=args.force)
    # 机器可读摘要，供脚本/CI 使用
    summary_path = os.path.join(args.output_dir, "batch_%s_summary.json" % args.type)
    os.makedirs(args.output_dir, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print("[batch] 摘要已写入 %s" % summary_path)
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
