"""batch_crawl 单元测试：活动关卡分类扩展（任务B）。

不依赖网络：用 mock 替换 requests.Session，验证 CATEGORY_MAP 注册、
list_category_titles 翻页逻辑、batch_crawl 类型校验和断点续爬。
"""

import json
import os
from unittest import mock

import pytest

from knowledge.crawler.batch_crawl import (CATEGORY_MAP, batch_crawl,
                                             list_category_titles)


class TestCategoryMap:
    def test_mainline_types_present(self):
        """主线类型（operator/enemy/stage）必须存在。"""
        assert "operator" in CATEGORY_MAP
        assert "enemy" in CATEGORY_MAP
        assert "stage" in CATEGORY_MAP

    def test_event_stage_types_present(self):
        """活动关卡类型（event_stage/annihilation/contingency）必须注册。"""
        assert "event_stage" in CATEGORY_MAP
        assert "annihilation" in CATEGORY_MAP
        assert "contingency" in CATEGORY_MAP

    def test_event_stage_uses_crawl_stage_method(self):
        """活动关卡复用 crawl_stage 解析方法（HTML 结构与主线类似）。"""
        assert CATEGORY_MAP["event_stage"][1] == "crawl_stage"
        assert CATEGORY_MAP["annihilation"][1] == "crawl_stage"
        assert CATEGORY_MAP["contingency"][1] == "crawl_stage"

    def test_event_stage_output_to_stages_event(self):
        """活动关卡输出到 stages_event/ 子目录，与主线 stages/ 区分。"""
        assert CATEGORY_MAP["event_stage"][2] == "stages_event"
        assert CATEGORY_MAP["annihilation"][2] == "stages_event"
        assert CATEGORY_MAP["contingency"][2] == "stages_event"

    def test_mainline_stage_output_to_stages(self):
        """主线关卡输出到 stages/。"""
        assert CATEGORY_MAP["stage"][2] == "stages"

    def test_unknown_type_raises(self):
        """未知类型抛 ValueError。"""
        with pytest.raises(ValueError, match="未知类型"):
            batch_crawl("nonexistent_type", limit=1)


class TestListCategoryTitles:
    def test_pagination_with_mock(self):
        """模拟 cmcontinue 翻页，验证能合并多页结果。"""
        page1 = {"query": {"categorymembers": [
            {"ns": 0, "title": "OF-1"}, {"ns": 0, "title": "OF-2"}]},
            "continue": {"cmcontinue": "page2"}}
        page2 = {"query": {"categorymembers": [
            {"ns": 0, "title": "OF-3"}]}}
        responses = [mock.Mock(status_code=200, json=lambda: page1),
                     mock.Mock(status_code=200, json=lambda: page2)]

        with mock.patch("knowledge.crawler.batch_crawl.requests.Session") as MockSession:
            session = MockSession.return_value
            session.get.side_effect = responses
            titles = list_category_titles("活动关卡", delay=0)
        assert titles == ["OF-1", "OF-2", "OF-3"]

    def test_limit_truncation(self):
        """limit 参数截断结果。"""
        page = {"query": {"categorymembers": [
            {"ns": 0, "title": "A"}, {"ns": 0, "title": "B"}, {"ns": 0, "title": "C"}]}}
        with mock.patch("knowledge.crawler.batch_crawl.requests.Session") as MockSession:
            session = MockSession.return_value
            session.get.return_value = mock.Mock(status_code=200, json=lambda: page)
            titles = list_category_titles("测试", limit=2, delay=0)
        assert titles == ["A", "B"]

    def test_skips_non_main_namespace(self):
        """cmnamespace=0 过滤后，非主命名空间成员被跳过。"""
        page = {"query": {"categorymembers": [
            {"ns": 0, "title": "OF-1"},
            {"ns": 14, "title": "Category:子分类"},  # 分类页，应跳过
            {"ns": 0, "title": "OF-2"}]}}
        with mock.patch("knowledge.crawler.batch_crawl.requests.Session") as MockSession:
            session = MockSession.return_value
            session.get.return_value = mock.Mock(status_code=200, json=lambda: page)
            titles = list_category_titles("测试", delay=0)
        assert titles == ["OF-1", "OF-2"]


class TestBatchCrawlResume:
    def test_skip_existing_json(self, tmp_path):
        """已存在且非空的 JSON 自动跳过（断点续爬）。"""
        # 预写一个已存在的 JSON
        json_dir = tmp_path / "stages_event"
        json_dir.mkdir()
        (json_dir / "OF-1.json").write_text('{"title": "OF-1"}', encoding="utf-8")

        # mock 标题列表（只返回 OF-1）
        with mock.patch("knowledge.crawler.batch_crawl.list_category_titles",
                        return_value=["OF-1"]):
            stats = batch_crawl("event_stage", limit=1, output_dir=str(tmp_path), delay=0)
        assert stats["skipped"] == 1
        assert stats["crawled"] == 0

    def test_force_recrawl_existing(self, tmp_path):
        """--force 时已存在的也重爬。"""
        json_dir = tmp_path / "stages_event"
        json_dir.mkdir()
        (json_dir / "OF-1.json").write_text('{"title": "OF-1"}', encoding="utf-8")

        with mock.patch("knowledge.crawler.batch_crawl.list_category_titles",
                        return_value=["OF-1"]):
            with mock.patch("knowledge.crawler.batch_crawl.PrtsCrawler") as MockCrawler:
                MockCrawler.return_value.crawl_stage.return_value = {"title": "OF-1", "new": True}
                stats = batch_crawl("event_stage", limit=1, output_dir=str(tmp_path),
                                    delay=0, force=True)
        assert stats["crawled"] == 1
        assert stats["skipped"] == 0

    def test_failed_page_does_not_abort(self, tmp_path):
        """单页爬取失败不中断整批，记录到 failed_titles。"""
        with mock.patch("knowledge.crawler.batch_crawl.list_category_titles",
                        return_value=["OF-1", "OF-2"]):
            with mock.patch("knowledge.crawler.batch_crawl.PrtsCrawler") as MockCrawler:
                crawler = MockCrawler.return_value
                crawler.crawl_stage.side_effect = [
                    Exception("解析失败"),  # OF-1 失败
                    {"title": "OF-2"},       # OF-2 成功
                ]
                stats = batch_crawl("event_stage", limit=2, output_dir=str(tmp_path), delay=0)
        assert stats["failed"] == 1
        assert stats["crawled"] == 1
        assert "OF-1" in stats["failed_titles"]
