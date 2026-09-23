"""PRTS Wiki 爬虫入口：抓取页面 HTML 并解析为 JSON。

合规约束（2026-09 探查 robots.txt 结论）：
- 只抓 /w/ 文章页（robots 明确 Allow /w/），不抓 /images/、/index.php、Special 页；
- 限速：默认 1 请求/秒；带重试（429/5xx 指数退避），异常 UA 会被站点屏蔽；
- 数据输出到 data/prts_raw/（已 gitignore，不进入公开仓库，版权风险）。

用法：
    from knowledge.crawler.prts_crawler import PrtsCrawler
    crawler = PrtsCrawler(output_dir="data/prts_raw")
    html = crawler.fetch_page("阿米娅")            # 抓取并缓存 HTML
    data = crawler.parse_operator_html(html)      # 解析为干员 JSON
"""

import os
import time

import requests

from .parse_enemies import parse_enemy
from .parse_guides import build_guides
from .parse_operators import parse_operator
from .parse_stages import parse_stage

__all__ = ["PrtsCrawler"]

BASE_URL = "https://prts.wiki/w/"
DEFAULT_UA = "arknights-llm-agent/0.1 (+research sample crawler; respectful 1 req/s)"
DEFAULT_DELAY = 1.0  # 秒/请求
MAX_RETRIES = 3


class PrtsCrawler(object):
    """PRTS Wiki 文本页爬虫（限速 + 重试 + 本地缓存）。"""

    def __init__(self, output_dir="data/prts_raw", delay=DEFAULT_DELAY, user_agent=DEFAULT_UA):
        # type: (str, float, str) -> None
        self.output_dir = output_dir
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self._last_request_ts = 0.0

    # ---------- 抓取 ----------

    def _rate_limit(self):
        """简单限速：距上次请求不足 delay 则等待。"""
        elapsed = time.time() - self._last_request_ts
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def fetch_page(self, title):
        # type: (str) -> str
        """抓取指定标题的 /w/ 页面，返回 HTML 文本（并写入本地缓存目录）。"""
        url = BASE_URL + title
        self._rate_limit()
        html_text = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code == 200:
                    html_text = resp.text
                    break
                if resp.status_code in (429, 500, 502, 503, 504):
                    # 被限速/临时错误：退避重试
                    wait = 2 ** attempt
                    print("[crawler] %s 返回 %s，%.0fs 后重试(%d/%d)"
                          % (title, resp.status_code, wait, attempt, MAX_RETRIES))
                    time.sleep(wait)
                    continue
                print("[crawler] %s 返回异常状态 %s，跳过" % (title, resp.status_code))
                return ""
            except requests.RequestException as exc:
                print("[crawler] %s 请求异常: %s，重试(%d/%d)" % (title, exc, attempt, MAX_RETRIES))
                time.sleep(2 ** attempt)
        if html_text is None:
            print("[crawler] %s 抓取失败（重试 %d 次后放弃）" % (title, MAX_RETRIES))
            return ""
        self._save_raw(title, html_text)
        return html_text

    # ---------- 保存 ----------

    def _save_raw(self, title, html_text):
        # type: (str, str) -> str
        """保存原始 HTML 到 data/prts_raw/html/，返回文件路径。"""
        safe = title.replace("/", "_").replace(":", "_")
        html_dir = os.path.join(self.output_dir, "html")
        os.makedirs(html_dir, exist_ok=True)
        path = os.path.join(html_dir, safe + ".html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_text)
        return path

    def _save_json(self, category, title, data):
        # type: (str, str, dict) -> str
        """保存解析后的 JSON 到 data/prts_raw/<category>/，返回文件路径。"""
        safe = title.replace("/", "_").replace(":", "_")
        cat_dir = os.path.join(self.output_dir, category)
        os.makedirs(cat_dir, exist_ok=True)
        path = os.path.join(cat_dir, safe + ".json")
        with open(path, "w", encoding="utf-8") as f:
            import json

            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    # ---------- 解析封装 ----------

    def crawl_operator(self, title):
        # type: (str) -> dict
        """抓取并解析干员页。"""
        html_text = self.fetch_page(title)
        if not html_text:
            return {}
        data = parse_operator(html_text)
        data["name"] = title
        self._save_json("operators", title, data)
        return data

    def crawl_enemy(self, title):
        # type: (str) -> dict
        """抓取并解析敌人页。"""
        html_text = self.fetch_page(title)
        if not html_text:
            return {}
        data = parse_enemy(html_text)
        data["name"] = title
        self._save_json("enemies", title, data)
        return data

    def crawl_stage(self, title):
        # type: (str) -> dict
        """抓取并解析关卡页。"""
        html_text = self.fetch_page(title)
        if not html_text:
            return {}
        data = parse_stage(html_text)
        data["name"] = title
        self._save_json("stages", title, data)
        return data

    def crawl_guides(self, operators=None, enemies=None, stages=None):
        # type: (list, list, list) -> list
        """由已解析 JSON 生成攻略文本块并保存到 data/prts_raw/guides.json。"""
        guides = build_guides(operators or [], enemies or [], stages or [])
        guides_dir = os.path.join(self.output_dir, "guides")
        os.makedirs(guides_dir, exist_ok=True)
        with open(os.path.join(guides_dir, "guides.json"), "w", encoding="utf-8") as f:
            import json

            json.dump(guides, f, ensure_ascii=False, indent=2)
        return guides
