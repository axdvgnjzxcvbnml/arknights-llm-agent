"""video_extract 单元测试（第十四批）。

分层：
- 配置/契约/mock 全链路/对齐与结构化：恒跑（纯标准库，不联网、无 GPU、无真实视频）；
- yt-dlp/ffmpeg/ASR/VLM 真实路径：用 monkeypatch 模拟"二进制/模型缺失"，断言抛 TODO-V100
  或明确错误，不触发真实抓取与推理。

运行：python -m pytest tests/test_video_extract.py -v
"""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
os.chdir(str(ROOT))

from video_extract import load_video_config  # noqa: E402
from video_extract.downloader import (  # noqa: E402
    MockDownloader, YtDlpDownloader, DownloaderError, extract_bv_id,
    categorize_video, is_allowed_category,
    CATEGORY_ARKNIGHTS, CATEGORY_ENDFIELD, CATEGORY_OTHER)
from video_extract.frame_extractor import (  # noqa: E402
    MockFrameExtractor, FFmpegFrameExtractor, FrameExtractError)
from video_extract.transcriber import (  # noqa: E402
    MockTranscriber, WhisperTranscriber, TranscriptSegment, build_transcriber)
from video_extract.chart_reader import (  # noqa: E402
    MockChartReader, VLMChartReader, build_chart_reader)
from video_extract.aligner import align, nearest_speech  # noqa: E402
from video_extract.structurer import build_sft, write_jsonl, format_timestamp  # noqa: E402


@pytest.fixture()
def cfg(tmp_path):
    """加载真实 config.yaml 但把所有输出目录重定向到临时目录（不碰 data/）。"""
    c = copy.deepcopy(load_video_config())
    c["download"]["out_dir"] = str(tmp_path / "video_raw")
    c["frames"]["out_root"] = str(tmp_path / "video_frames")
    c["structure"]["out_jsonl"] = str(tmp_path / "sft" / "video.jsonl")
    return c


def _run_pipeline(c, bv="BV1MOCK00001", url=None, duration=30.0):
    url = url or ("https://www.bilibili.com/video/%s" % bv)
    meta = MockDownloader(c).download(url)
    frames = MockFrameExtractor(c).extract(
        meta.bv_id, duration_sec=duration, video_path=meta.video_path)
    segs = MockTranscriber(c).transcribe(meta.audio_path)
    charts = MockChartReader(c).read_all(frames)
    pairs = align(segs, charts, config=c)
    records = build_sft(pairs, meta, c)
    return meta, frames, segs, charts, pairs, records


# ---------------- import 轻量 ----------------
class TestNoHeavyImports:
    def test_import_video_extract_is_stdlib_only(self):
        # 干净子进程证明：import video_extract 本身不拉起 GPU/视觉/数值栈
        code = (
            "import sys; "
            "import video_extract; "
            "from video_extract import downloader, frame_extractor, transcriber, "
            "chart_reader, aligner, structurer; "
            "banned=['torch','transformers','numpy','cv2','whisper','faster_whisper']; "
            "bad=[m for m in banned if m in sys.modules]; "
            "print('BAD', bad); sys.exit(1 if bad else 0)")
        proc = subprocess.run([sys.executable, "-c", code],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert proc.returncode == 0, proc.stdout.decode() + proc.stderr.decode()
        assert b"BAD []" in proc.stdout


# ---------------- 配置 / 工具 ----------------
class TestConfig:
    def test_required_sections_present(self):
        c = load_video_config()
        for s in ("uploaders", "download", "frames", "asr", "vlm", "align", "structure"):
            assert s in c

    def test_missing_section_raises(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("download: {}\n", encoding="utf-8")
        with pytest.raises(ValueError):
            load_video_config(str(bad))

    @pytest.mark.parametrize("raw,expect", [
        ("https://www.bilibili.com/video/BV1xx411c7mD", "BV1xx411c7mD"),
        ("BV1xx411c7mD", "BV1xx411c7mD"),
        ("", ""),
        ("https://bilibili.com/video/xxx?p=1", "https://bilibili.com/video/xxx?p=1"),
    ])
    def test_extract_bv_id(self, raw, expect):
        assert extract_bv_id(raw) == expect


# ---------------- 视频分类过滤（第十五批）----------------
class TestCategorize:
    @pytest.mark.parametrize("title,expect,matched", [
        ("明日方舟3-8攻略", CATEGORY_ARKNIGHTS, "明日方舟"),
        ("血狼破军：危机合约干员强度榜", CATEGORY_ARKNIGHTS, "干员"),
        ("肉鸽仙术杯登顶思路 干员讲解", CATEGORY_ARKNIGHTS, "干员"),
        ("终末地实机演示", CATEGORY_ENDFIELD, "终末地"),
        ("Endfield 公测前瞻", CATEGORY_ENDFIELD, "Endfield"),
        # 两边都命中：终末地优先（排除），防止污染
        ("明日方舟终末地对比", CATEGORY_ENDFIELD, "终末地"),
        ("从明日方舟看到终末地的进化", CATEGORY_ENDFIELD, "终末地"),
        ("今天打一把别的游戏", CATEGORY_OTHER, ""),
    ])
    def test_title_categorization(self, cfg, title, expect, matched):
        cat, kw = categorize_video(title=title, config=cfg)
        assert cat == expect
        assert kw == matched if expect != CATEGORY_OTHER else kw == ""

    def test_case_insensitive_endfield(self, cfg):
        assert categorize_video(title="endfield ENDFIELD", config=cfg)[0] == CATEGORY_ENDFIELD

    def test_tags_can_classify_even_with_plain_title(self, cfg):
        # 标题不含关键词，但分区/标签含"干员/终末地"
        cat, _ = categorize_video(title="这周聊点新东西",
                                  tags=["游戏", "明日方舟干员评测"], config=cfg)
        assert cat == CATEGORY_ARKNIGHTS
        cat2, _ = categorize_video(title="随便起的标题",
                                   tags=["Endfield"], config=cfg)
        assert cat2 == CATEGORY_ENDFIELD

    def test_default_only_arknights_allowed(self, cfg):
        assert is_allowed_category(CATEGORY_ARKNIGHTS, cfg)
        assert not is_allowed_category(CATEGORY_ENDFIELD, cfg)
        assert not is_allowed_category(CATEGORY_OTHER, cfg)

    def test_allowed_categories_override(self, cfg):
        cfg["categorize"]["allowed_categories"] = ["arknights", "endfield"]
        assert is_allowed_category(CATEGORY_ENDFIELD, cfg)

    def test_empty_title_safe(self, cfg):
        assert categorize_video(title="", config=cfg)[0] == CATEGORY_OTHER


# ---------------- downloader ----------------
class TestMockDownloader:
    def test_download_writes_meta_and_parses_bv(self, cfg):
        dl = MockDownloader(cfg)
        meta = dl.download("https://www.bilibili.com/video/BV1abCdef123")
        assert meta.bv_id == "BV1abCdef123"
        assert meta.is_mock is True
        # 默认 mock 标题含"危机合约/干员" -> arknights
        assert meta.category == CATEGORY_ARKNIGHTS and meta.category_matched
        meta_path = os.path.join(cfg["download"]["out_dir"], meta.bv_id, "meta.json")
        assert os.path.exists(meta_path)
        with open(meta_path, encoding="utf-8") as f:
            loaded = json.load(f)
            assert loaded["bv_id"] == meta.bv_id
            assert loaded["category"] == CATEGORY_ARKNIGHTS

    def test_batch_excludes_endfield_before_processing(self, cfg):
        dl = MockDownloader(cfg)
        ark_url = "https://www.bilibili.com/video/BV1aa0000001"
        end_url = "https://www.bilibili.com/video/BV1bb0000002"
        items = {
            ark_url: {"title": "明日方舟 剿灭作战 400 杀挂机攻略"},
            end_url: {"title": "终末地 Boss 战 实机"},
        }
        res = dl.batch_download([ark_url, end_url], items=items)
        assert [m.bv_id for m in res["downloaded"]] == ["BV1aa0000001"]
        assert res["downloaded"][0].category == CATEGORY_ARKNIGHTS
        assert res["excluded"][0]["category"] == CATEGORY_ENDFIELD
        # 被排除的终末地不应落 meta / 建目录（下载前剔除）
        assert not os.path.exists(os.path.join(
            cfg["download"]["out_dir"], "BV1bb0000002", "meta.json"))

    def test_categorize_items_partition(self, cfg):
        dl = MockDownloader(cfg)
        items = [
            {"id": "1", "title": "明日方舟干员评测", "url": "u1"},
            {"id": "2", "title": "终末地探索", "url": "u2"},
            {"id": "3", "title": "无关视频", "url": "u3"},
        ]
        allowed, excluded = dl.categorize_items(items)
        assert [x["id"] for x in allowed] == ["1"]
        assert sorted(x["id"] for x in excluded) == ["2", "3"]

    def test_batch_resume_skips_existing(self, cfg):
        dl = MockDownloader(cfg)
        url = "https://www.bilibili.com/video/BV1MOCK00001"
        first = dl.batch_download([url])
        assert len(first["downloaded"]) == 1 and first["skipped"] == []
        second = dl.batch_download([url])
        assert second["downloaded"] == [] and second["skipped"] == ["BV1MOCK00001"]


class TestRealDownloaderGuards:
    def test_missing_ytdlp_bin_raises(self, cfg, monkeypatch):
        monkeypatch.setattr("video_extract.downloader.shutil.which", lambda _b: None)
        with pytest.raises(DownloaderError):
            YtDlpDownloader(cfg).download("https://www.bilibili.com/video/BV1MOCK00001")

    def test_empty_uid_raises(self, cfg, monkeypatch):
        # 模拟 yt-dlp 存在（但不真正执行），UID 为空应在抓取前明确报错
        monkeypatch.setattr("video_extract.downloader.shutil.which",
                            lambda _b: "/usr/local/bin/yt-dlp")
        with pytest.raises(DownloaderError):
            YtDlpDownloader(cfg).list_uploader_videos(uid="")


# ---------------- frame extractor ----------------
class TestFrameExtractor:
    def test_mock_manifest_timestamps_and_placeholder(self, cfg):
        cfg["frames"]["interval_sec"] = 5
        frames = MockFrameExtractor(cfg).extract("BV1MOCK00001", duration_sec=20)
        ts = [f.timestamp_sec for f in frames]
        assert ts == [0.0, 5.0, 10.0, 15.0, 20.0]
        manifest = os.path.join(cfg["frames"]["out_root"], "BV1MOCK00001", "manifest.json")
        with open(manifest, encoding="utf-8") as f:
            m = json.load(f)
        assert m["placeholder"] is True and m["count"] == len(frames)

    def test_real_extractor_missing_ffmpeg_raises(self, cfg, monkeypatch):
        monkeypatch.setattr("video_extract.frame_extractor.shutil.which", lambda _b: None)
        with pytest.raises(FrameExtractError):
            FFmpegFrameExtractor(cfg).extract("/no/such/video.mp4", "BV1")

    def test_real_extractor_missing_video_raises(self, cfg, monkeypatch):
        monkeypatch.setattr("video_extract.frame_extractor.shutil.which",
                            lambda b: "/usr/bin/" + b)
        with pytest.raises(FrameExtractError):
            FFmpegFrameExtractor(cfg).extract("/no/such/video.mp4", "BV1")


# ---------------- transcriber / chart reader ----------------
class TestTranscriber:
    def test_mock_segments_sorted_and_shaped(self, cfg):
        segs = MockTranscriber(cfg).transcribe("ignored.wav")
        assert all(set(s) == {"start", "end", "text"} for s in segs)
        assert all(s["end"] > s["start"] for s in segs)
        assert [s["start"] for s in segs] == sorted(s["start"] for s in segs)

    def test_whisper_todo_v100_without_model(self, cfg, tmp_path):
        wav = tmp_path / "a.wav"
        wav.write_bytes(b"RIFFstub")  # 文件存在，卡在模型加载而非音频检查
        cfg["asr"]["backend"] = "whisper"
        cfg["asr"]["model"] = ""
        t = build_transcriber(cfg)
        assert isinstance(t, WhisperTranscriber)
        with pytest.raises(NotImplementedError) as ei:
            t.transcribe(str(wav))
        assert "TODO-V100" in str(ei.value)

    def test_factory_returns_mock(self, cfg):
        cfg["asr"]["backend"] = "mock"
        assert isinstance(build_transcriber(cfg), MockTranscriber)


class TestChartReader:
    def test_mock_charts_anchor_to_nearest_frames(self, cfg):
        frames = MockFrameExtractor(cfg).extract("BV1", duration_sec=30)
        charts = MockChartReader(cfg).read_all(frames)
        types = {c.chart_type: c.timestamp_sec for c in charts}
        assert types["table"] == 10.0      # 锚点 12 吸附到最近帧 10
        assert types["tier_list"] == 20.0  # 锚点 21 吸附到最近帧 20
        for c in charts:
            assert c.operator == "银灰"
            assert c.evidence == "retrieved:video_frame"
            assert c.confidence >= cfg["vlm"]["confidence_threshold"]

    def test_vlm_todo_v100_without_model(self, cfg, tmp_path):
        img = tmp_path / "f.jpg"
        img.write_bytes(b"jpegstub")
        cfg["vlm"]["backend"] = "qwen3vl"
        cfg["vlm"]["model"] = ""
        r = build_chart_reader(cfg)
        assert isinstance(r, VLMChartReader)
        with pytest.raises(NotImplementedError) as ei:
            r.read_chart(str(img), 12.0)
        assert "TODO-V100" in str(ei.value)

    def test_empty_frames_safe(self, cfg):
        assert MockChartReader(cfg).read_all([]) == []
        assert isinstance(build_chart_reader(cfg), MockChartReader)


# ---------------- aligner ----------------
class TestAligner:
    def test_containing_segment_preferred(self):
        tr = [{"start": 8, "end": 16, "text": "A"}]
        speech, delta, matched = nearest_speech(12.0, tr, tolerance=8)
        assert matched is True and speech["text"] == "A" and delta == 0.0

    def test_nearest_within_tolerance(self):
        tr = [TranscriptSegment(0, 5, "x").to_dict(),
              TranscriptSegment(20, 25, "y").to_dict()]
        speech, _d, matched = nearest_speech(18.0, tr, tolerance=5)
        assert matched and speech["text"] == "y"

    def test_beyond_tolerance_unmatched(self):
        tr = [{"start": 0, "end": 4, "text": "far"}]
        speech, delta, matched = nearest_speech(100.0, tr, tolerance=8)
        assert matched is False and speech is None and abs(delta) == 98.0

    def test_empty_transcript(self):
        speech, delta, matched = nearest_speech(10, [], tolerance=8)
        assert (speech, matched) == (None, False)

    def test_align_empty_charts(self):
        assert align([{"start": 0, "end": 1, "text": "x"}], [], tolerance=8) == []


# ---------------- structurer ----------------
class TestStructurer:
    def test_full_pipeline_records(self, cfg):
        _, frames, segs, charts, pairs, records = _run_pipeline(cfg)
        assert len(records) == len(charts) == 2
        table_rec = next(r for r in records if r["meta"]["chart_type"] == "table")
        ans = table_rec["answer"]
        assert "BV1MOCK00001" in ans and "00:10" in ans
        assert "DPS=1820" in ans and "DPH=880" in ans
        assert "口播要点" in ans and "第三方分析" in ans
        ev = table_rec["meta"]["evidence"]
        assert ev["chart"] == "retrieved:video_frame"
        assert ev["speech"] == "retrieved:video_audio"
        assert ev["alignment"] == "inferred:timestamp"
        assert table_rec["meta"]["timestamps"]["chart"] == 10.0
        assert "银灰" in table_rec["question"] and "危机合约" in table_rec["question"]

    def test_tier_record_has_tier(self, cfg):
        _, _, _, _, _, records = _run_pipeline(cfg)
        tier = next(r for r in records if r["meta"]["chart_type"] == "tier_list")
        assert "T0" in tier["answer"] and "档位" in tier["question"]

    def test_empty_pairs_safe(self, cfg):
        assert build_sft([], {"bv_id": "BV", "title": "t"}, cfg) == []

    def test_write_jsonl_roundtrip(self, cfg):
        recs = [{"question": "q", "answer": "a", "meta": {"bv_id": "BV1"}}]
        path = str(Path(cfg["structure"]["out_jsonl"]))
        assert write_jsonl(recs, path) == 1
        with open(path, encoding="utf-8") as f:
            back = [json.loads(line) for line in f if line.strip()]
        assert back[0]["meta"]["bv_id"] == "BV1"

    def test_unmatched_speech_marked(self, cfg):
        # 口播时间轴与图表相距很远 -> 记录仍生成，但 speech 证据为 None、对齐标 unmatched
        frames = MockFrameExtractor(cfg).extract("BV1", duration_sec=200)
        charts = MockChartReader(cfg).read_all(frames)
        segs = [{"start": 0, "end": 2, "text": "很早的开场白"}]
        pairs = align(segs, charts, config=cfg)
        assert any(not p["matched"] for p in pairs)
        recs = build_sft(pairs, {"bv_id": "BV1", "title": "t"}, cfg)
        unmatched = [r for r in recs if not r["meta"]["speech_matched"]]
        assert unmatched and unmatched[0]["meta"]["evidence"]["speech"] is None

    @pytest.mark.parametrize("sec,text", [(0, "00:00"), (65, "01:05"), (3599, "59:59")])
    def test_format_timestamp(self, sec, text):
        assert format_timestamp(sec) == text
