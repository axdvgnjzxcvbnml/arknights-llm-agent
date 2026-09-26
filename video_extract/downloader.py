# TODO-V100: 本模块不需要 GPU；真实抓取在能联网、已安装 yt-dlp/ffmpeg 的机器上运行。
# 沙箱只跑 MockDownloader。ASR/VLM（下游模块）才需要 V100。
"""视频/音频下载：封装 yt-dlp（走 CLI，subprocess 调用，不强依赖 yt_dlp Python 包）。

能力：
- download(url)：下载单个视频（bestvideo+bestaudio 合并 mp4），并抽一条 16k 单声道 wav；
  同时落 info.json，解析成 VideoMeta（标题/发布时间/BV 号/时长）。
- list_uploader_videos(uid)：用 --flat-playlist --dump-json 拉取 UP 主投稿列表。
- batch_download(...)：批量下载，限速 + 指数退避重试 + 断点续爬（已存在 meta 的跳过）。

礼貌抓取 / 合规：
- 限速 rate_limit、请求间隔 sleep_interval、单次批量上限 max_videos_per_run；
- respect_robots=true 时先校验 https://www.bilibili.com/robots.txt，不允许则中止；
- 素材只写 data/video_raw/（gitignore），仓库不保存任何视频/音频。

import 本模块不拉起第三方包（subprocess/urllib 均为标准库）。
"""

import json
import os
import re
import shutil
import subprocess
import time
import urllib.robotparser
from dataclasses import asdict, dataclass, field

from . import DEFAULT_CONFIG_PATH, load_video_config

__all__ = ["VideoMeta", "DownloaderError", "YtDlpDownloader", "MockDownloader",
           "extract_bv_id", "categorize_video", "is_allowed_category",
           "allowed_categories", "CATEGORY_ARKNIGHTS", "CATEGORY_ENDFIELD", "CATEGORY_OTHER"]

_BV_RE = re.compile(r"(BV[0-9A-Za-z]{10})")
_BILIBILI_ROBOTS = "https://www.bilibili.com/robots.txt"

# 视频分类（第十五批）
CATEGORY_ARKNIGHTS = "arknights"
CATEGORY_ENDFIELD = "endfield"
CATEGORY_OTHER = "other"

_DEFAULT_ENDFIELD_KW = ["终末地", "Endfield"]
_DEFAULT_ARKNIGHTS_KW = ["明日方舟", "干员", "危机合约", "肉鸽", "剿灭"]


def _kw_list(cfg, key, default):
    cat = (cfg or {}).get("categorize", {}) if isinstance(cfg, dict) else {}
    kws = cat.get(key) or default
    return [str(k) for k in kws]


def allowed_categories(cfg):
    """返回放行分类列表；缺省只放行 arknights。"""
    cat = (cfg or {}).get("categorize", {}) if isinstance(cfg, dict) else {}
    allow = cat.get("allowed_categories") or [CATEGORY_ARKNIGHTS]
    return [str(x) for x in allow]


def is_allowed_category(category, cfg):
    # type: (str, dict) -> bool
    """该分类是否在 categorize.allowed_categories 放行名单内。"""
    return category in allowed_categories(cfg)


def categorize_video(title="", tags=None, config=None, config_path=DEFAULT_CONFIG_PATH):
    # type: (str, object, object, str) -> tuple
    """按标题 + 分区标签判定视频分类，返回 (category, matched_keyword)。

    优先级（关键）：endfield > arknights > other。
    因此"明日方舟终末地对比"这类两边都命中的标题判 endfield（排除）。
    标题与标签拼成同一文本做大小写不敏感匹配；纯函数、无 IO，便于单测。
    """
    cfg = config or load_video_config(config_path)
    endfield_kw = _kw_list(cfg, "endfield_keywords", _DEFAULT_ENDFIELD_KW)
    ark_kw = _kw_list(cfg, "arknights_keywords", _DEFAULT_ARKNIGHTS_KW)

    tag_list = tags or []
    if isinstance(tag_list, (str, bytes)):
        tag_list = [tag_list]
    blob = str(title or "")
    for t in tag_list:
        blob += " " + str(t)
    low = blob.lower()

    # 1) 终末地优先（排除项），即使同时含"明日方舟"
    for kw in endfield_kw:
        if kw.lower() in low:
            return CATEGORY_ENDFIELD, kw
    # 2) 明日方舟
    for kw in ark_kw:
        if kw.lower() in low:
            return CATEGORY_ARKNIGHTS, kw
    # 3) 其他
    return CATEGORY_OTHER, ""


class DownloaderError(RuntimeError):
    """下载错误：yt-dlp/ffmpeg 缺失、被 robots 拒绝、命令失败或重试耗尽。"""


@dataclass
class VideoMeta(object):
    """单个视频的元数据（与 data/video_raw/<BV>/meta.json 对应）。"""

    bv_id: str = ""
    title: str = ""
    webpage_url: str = ""
    uploader: str = ""
    publish_time: str = ""        # yt-dlp upload_date，形如 20240501
    duration_sec: float = 0.0
    video_path: str = ""
    audio_path: str = ""
    is_mock: bool = False
    category: str = ""            # arknights | endfield | other（第十五批）
    category_matched: str = ""    # 命中的关键词，便于审计为何这样分类
    tags: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def extract_bv_id(url_or_bv):
    # type: (str) -> str
    """从 URL 或裸串里提取 BV 号；提取不到时返回去空白的原值。"""
    if not url_or_bv:
        return ""
    m = _BV_RE.search(url_or_bv)
    return m.group(1) if m else url_or_bv.strip()


class YtDlpDownloader(object):
    """yt-dlp 真实下载器（纯 CPU/联网）。沙箱不实际调用，方法逻辑保留可直接用。"""

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        cfg = config or load_video_config(config_path)
        self.config = cfg
        d = cfg.get("download", {})
        self.bin = d.get("yt_dlp_bin", "yt-dlp")
        self.out_dir = d.get("out_dir", "data/video_raw")
        self.rate_limit = str(d.get("rate_limit", "500K"))
        self.sleep_interval = int(d.get("sleep_interval", 1))
        self.max_sleep_interval = int(d.get("max_sleep_interval", 3))
        self.request_retries = int(d.get("request_retries", 3))
        self.backoff_base = float(d.get("backoff_base", 2.0))
        self.respect_robots = bool(d.get("respect_robots", True))
        self.merge_format = d.get("merge_format", "mp4")
        self.extract_audio = bool(d.get("extract_audio", True))
        self.audio_format = d.get("audio_format", "wav")
        self.audio_sr = int(d.get("audio_sample_rate", 16000))
        self.audio_ch = int(d.get("audio_channels", 1))
        frames_cfg = cfg.get("frames", {})
        self.ffmpeg_bin = frames_cfg.get("ffmpeg_bin", "ffmpeg")

    # ---------- 环境/合规 ----------
    def is_available(self):
        return shutil.which(self.bin) is not None

    def _ensure_available(self):
        if not self.is_available():
            raise DownloaderError(
                "未找到 yt-dlp 可执行文件 %r。请 pip install yt-dlp 或在 "
                "video_extract/config.yaml 配置 download.yt_dlp_bin 绝对路径。" % self.bin)

    def robots_allows(self, url):
        # type: (str) -> bool
        """校验 B 站 robots.txt 是否允许抓取该 URL；无法判定时按保守策略拒绝。"""
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(_BILIBILI_ROBOTS)
        try:
            rp.read()
        except Exception as exc:  # 网络失败/解析失败都不绕过
            raise DownloaderError("无法获取 robots.txt（%s），保守起见中止抓取。" % exc)
        # yt-dlp 走标准 UA；用通配规则判定
        return rp.can_fetch("*", url)

    # ---------- 子进程 ----------
    def _run(self, args, timeout=1800):
        # type: (list, int) -> subprocess.CompletedProcess
        last_err = None
        for attempt in range(self.request_retries):
            proc = subprocess.run(args, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=timeout)
            if proc.returncode == 0:
                return proc
            last_err = proc.stderr.decode("utf-8", "ignore")[-800:]
            # 简单指数退避，避免被限流时立刻重放
            time.sleep(self.backoff_base ** attempt)
        raise DownloaderError("命令重试 %d 次仍失败: %s\n%s"
                              % (self.request_retries, " ".join(args[:3]), last_err))

    # ---------- 单视频 ----------
    def download(self, url):
        # type: (str) -> VideoMeta
        self._ensure_available()
        if self.respect_robots and not self.robots_allows(url):
            raise DownloaderError("robots.txt 不允许抓取该 URL，已中止: %s" % url)
        os.makedirs(self.out_dir, exist_ok=True)
        out_tmpl = os.path.join(self.out_dir, "%(id)s", "%(title).80s.%(ext)s")
        args = [
            self.bin, "--no-playlist",
            "--retries", str(self.request_retries),
            "--limit-rate", self.rate_limit,
            "--sleep-interval", str(self.sleep_interval),
            "--max-sleep-interval", str(self.max_sleep_interval),
            "-f", "bestvideo*+bestaudio/best",
            "--merge-output-format", self.merge_format,
            "--write-info-json",
            "-o", out_tmpl, url,
        ]
        self._run(args)
        bv = extract_bv_id(url)
        meta = self._meta_from_info(bv)
        if self.extract_audio and meta.video_path:
            meta.audio_path = self._extract_audio(meta.video_path, meta.bv_id)
        self._write_meta(meta)
        return meta

    def _extract_audio(self, video_path, bv):
        if shutil.which(self.ffmpeg_bin) is None:
            raise DownloaderError("抽音轨需要 ffmpeg，但 PATH 中未找到 %r。" % self.ffmpeg_bin)
        wav = os.path.join(self.out_dir, bv, bv + "." + self.audio_format)
        args = [self.ffmpeg_bin, "-y", "-i", video_path, "-vn",
                "-acodec", "pcm_s16le", "-ar", str(self.audio_sr),
                "-ac", str(self.audio_ch), wav]
        self._run(args, timeout=900)
        return wav

    def _info_path(self, bv):
        d = os.path.join(self.out_dir, bv)
        if not os.path.isdir(d):
            return ""
        for name in os.listdir(d):
            if name.endswith(".info.json"):
                return os.path.join(d, name)
        return ""

    def _meta_from_info(self, bv):
        # type: (str) -> VideoMeta
        info_path = self._info_path(bv)
        if not info_path:
            raise DownloaderError("下载后未找到 info.json（BV=%s）。" % bv)
        with open(info_path, "r", encoding="utf-8") as f:
            info = json.load(f)
        d = os.path.dirname(info_path)
        video_path = ""
        for name in os.listdir(d):
            if name.lower().endswith((".mp4", ".mkv", ".webm", ".flv")):
                video_path = os.path.join(d, name)
                break
        bv_id = str(info.get("id") or bv)
        tags = info.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        category, matched = categorize_video(
            title=info.get("title", ""), tags=tags, config=self.config)
        return VideoMeta(
            bv_id=bv_id,
            title=info.get("title", ""),
            webpage_url=info.get("webpage_url", ""),
            uploader=info.get("uploader") or info.get("channel") or "",
            publish_time=str(info.get("upload_date", "")),
            duration_sec=float(info.get("duration") or 0.0),
            video_path=video_path,
            category=category,
            category_matched=matched,
            tags=list(tags),
        )

    def _write_meta(self, meta):
        path = os.path.join(self.out_dir, meta.bv_id, "meta.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta.to_dict(), f, ensure_ascii=False, indent=2)

    # ---------- UP 主批量 ----------
    def list_uploader_videos(self, uid, limit=None):
        # type: (str, int) -> list
        """返回 UP 主投稿页的 [{id,title,url}]（--flat-playlist --dump-json）。"""
        self._ensure_available()
        if not uid:
            raise DownloaderError("未配置 UP 主 UID（video_extract/config.yaml uploaders.uid）。")
        url = "https://space.bilibili.com/%s/video" % uid
        if self.respect_robots and not self.robots_allows(url):
            raise DownloaderError("robots.txt 不允许抓取 UP 主列表页，已中止: %s" % url)
        args = [self.bin, "--flat-playlist", "--dump-json", "--no-warnings", url]
        proc = self._run(args, timeout=900)
        items = []
        cap = int(limit) if limit else int(self.max_videos_per_run_default())
        for line in proc.stdout.decode("utf-8", "ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            items.append({
                "id": str(obj.get("id", "")),
                "title": obj.get("title", ""),
                "url": obj.get("url") or obj.get("webpage_url") or "",
            })
            if len(items) >= cap:
                break
        return items

    def max_videos_per_run_default(self):
        # 从配置再读一次上限（list 场景的默认 cap）
        cfg = load_video_config(DEFAULT_CONFIG_PATH)
        return cfg.get("download", {}).get("max_videos_per_run", 5)

    def categorize_items(self, items):
        """给 list_uploader_videos 的条目按标题补 category/category_matched。

        flat-playlist 阶段一般只有标题、没有标签；下载后还会用 info.json 的
        真实 tags 复核一次。返回 (allowed_items, excluded_items)。
        """
        allowed, excluded = [], []
        for it in items or []:
            category, matched = categorize_video(
                title=it.get("title", ""), tags=it.get("tags"), config=self.config)
            enriched = dict(it)
            enriched["category"] = category
            enriched["category_matched"] = matched
            if is_allowed_category(category, self.config):
                allowed.append(enriched)
            else:
                excluded.append(enriched)
        return allowed, excluded

    def plan_uploader_videos(self, uid, limit=None):
        """拉 UP 主列表并按分类过滤，返回 {"allowed":[...], "excluded":[...]}。

        终末地/其他在下载前就被剔除，省带宽且保证它们不进入抽帧/转写/结构化。
        """
        items = self.list_uploader_videos(uid, limit=limit)
        allowed, excluded = self.categorize_items(items)
        return {"allowed": allowed, "excluded": excluded}

    def batch_download(self, urls, on_skip=None, items=None):
        # type: (list, object, object) -> dict
        """逐个下载，限速间隔；已存在 meta 的跳过（断点续爬），单个失败不中断整批。

        items（可选）：{url: {"title":..,"tags":..}}，来自投稿列表；提供时对不在
        allowed_categories 的视频**下载前**剔除并记入 excluded（终末地等不下载）。

        返回 {"downloaded":[VideoMeta...], "skipped":[bv...],
              "excluded":[{url,title,category}], "failed":[{url,error}]}。
        """
        items = items or {}
        result = {"downloaded": [], "skipped": [], "excluded": [], "failed": []}
        for i, url in enumerate(urls):
            bv = extract_bv_id(url)
            pre = items.get(url) or items.get(bv) or {}
            if pre:
                category, matched = categorize_video(
                    title=pre.get("title", ""), tags=pre.get("tags"),
                    config=self.config)
                if not is_allowed_category(category, self.config):
                    result["excluded"].append({
                        "url": url, "title": pre.get("title", ""),
                        "category": category, "matched": matched})
                    continue
            meta_path = os.path.join(self.out_dir, bv, "meta.json")
            if os.path.exists(meta_path):
                result["skipped"].append(bv)
                if on_skip:
                    on_skip(bv)
                continue
            try:
                meta = self.download(url)
                # 下载后用真实 tags 复核：即便下载了，非放行分类也标进 excluded
                # （由下游流水线据 meta.category 再次拦截，双保险）
                if not is_allowed_category(meta.category, self.config):
                    result["excluded"].append({
                        "url": url, "title": meta.title,
                        "category": meta.category,
                        "matched": meta.category_matched, "bv": bv})
                else:
                    result["downloaded"].append(meta)
            except DownloaderError as exc:
                result["failed"].append({"url": url, "error": str(exc)})
            if i < len(urls) - 1:
                time.sleep(max(self.sleep_interval, 1))  # 礼貌限速
        return result


class MockDownloader(object):
    """确定性假下载：不联网、不产生真实视频，只落 meta.json，供 CPU 闭环验证。"""

    DEFAULT_META = VideoMeta(
        bv_id="BV1MOCK00001",
        title="【血狼破军】危机合约干员输出与强度分析（mock 样例）",
        webpage_url="https://www.bilibili.com/video/BV1MOCK00001",
        uploader="血狼破军",
        publish_time="20240501",
        duration_sec=30.0,
        is_mock=True,
    )

    def __init__(self, config=None, config_path=DEFAULT_CONFIG_PATH):
        cfg = config or load_video_config(config_path)
        self.config = cfg
        self.out_dir = cfg.get("download", {}).get("out_dir", "data/video_raw")

    def is_available(self):
        return True

    def categorize_items(self, items):
        """与 YtDlpDownloader.categorize_items 相同的下载前分类（mock）。"""
        allowed, excluded = [], []
        for it in items or []:
            category, matched = categorize_video(
                title=it.get("title", ""), tags=it.get("tags"), config=self.config)
            enriched = dict(it)
            enriched["category"] = category
            enriched["category_matched"] = matched
            (allowed if is_allowed_category(category, self.config) else excluded).append(enriched)
        return allowed, excluded

    def download(self, url=None, bv_id=None, meta=None, title=None, tags=None):
        m = VideoMeta(**asdict(meta)) if meta is not None else VideoMeta(**asdict(self.DEFAULT_META))
        if bv_id:
            m.bv_id = bv_id
        elif url:
            parsed = extract_bv_id(url)
            if parsed and not parsed.startswith("http"):
                m.bv_id = parsed
        if title:
            m.title = title
        if tags is not None:
            m.tags = list(tags)
        category, matched = categorize_video(
            title=m.title, tags=m.tags, config=self.config)
        m.category, m.category_matched = category, matched
        # mock 不写真实视频/音频，仅给路径占位与 meta.json，下游 mock 不读取媒体内容
        m.video_path = os.path.join(self.out_dir, m.bv_id, m.bv_id + ".mp4")
        m.audio_path = os.path.join(self.out_dir, m.bv_id, m.bv_id + ".wav")
        m.is_mock = True
        d = os.path.join(self.out_dir, m.bv_id)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(m.to_dict(), f, ensure_ascii=False, indent=2)
        return m

    def list_uploader_videos(self, uid=None, limit=3):
        n = int(limit) if limit else 3
        titles = [
            "【血狼破军】明日方舟3-8攻略（mock %d）" % i if i % 2 else
            "终末地实机演示 血狼破军 mock %d" % i
            for i in range(1, n + 1)
        ]
        return [
            {"id": "BV1MOCK%05d" % i, "title": titles[i - 1],
             "url": "https://www.bilibili.com/video/BV1MOCK%05d" % i}
            for i in range(1, n + 1)
        ]

    def batch_download(self, urls, on_skip=None, items=None):
        items = items or {}
        result = {"downloaded": [], "skipped": [], "excluded": [], "failed": []}
        for url in urls:
            bv = extract_bv_id(url)
            pre = items.get(url) or items.get(bv) or {}
            if pre:
                category, matched = categorize_video(
                    title=pre.get("title", ""), tags=pre.get("tags"),
                    config=self.config)
                if not is_allowed_category(category, self.config):
                    result["excluded"].append({
                        "url": url, "title": pre.get("title", ""),
                        "category": category, "matched": matched})
                    continue
            if os.path.exists(os.path.join(self.out_dir, bv, "meta.json")):
                result["skipped"].append(bv)
                if on_skip:
                    on_skip(bv)
                continue
            result["downloaded"].append(
                self.download(url=url, title=pre.get("title"), tags=pre.get("tags")))
        return result
