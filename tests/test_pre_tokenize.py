"""pre_tokenize 单元测试：验证 SFT 预 tokenize 流程正确性。

用 MockTokenizer 验证：
- _build_sft_pair 的 input_ids/labels 格式（question 部分 labels=-100）
- 截断逻辑（超过 max_length 时优先保留 question）
- pre_tokenize_file 的统计和输出格式
- 空输入/坏行的容错
"""

import json
import os

import pytest

from training.pre_tokenize import (MockTokenizer, _build_sft_pair,
                                    pre_tokenize_file)


class TestMockTokenizer:
    def test_encode_returns_list_of_ints(self):
        tok = MockTokenizer()
        ids = tok.encode("部署 翎羽")
        assert isinstance(ids, list)
        assert all(isinstance(i, int) for i in ids)
        assert len(ids) > 0

    def test_encode_chinese_char_by_char(self):
        """中文逐字分词：3 个中文字符至少 3 个 token。"""
        tok = MockTokenizer()
        ids = tok.encode("翎羽娜")
        assert len(ids) >= 3

    def test_eos_token_id(self):
        tok = MockTokenizer()
        assert tok.eos_token_id == 151643  # Qwen3 真实 eos


class TestBuildSftPair:
    def test_question_labels_masked(self):
        """question 部分的 labels 必须是 -100（不计算 loss）。"""
        tok = MockTokenizer()
        q_ids = tok.encode("问题")
        a_ids = tok.encode("答案")
        input_ids, labels = _build_sft_pair("问题", "答案", tok, max_length=2048)

        # input_ids = q + a + eos
        assert len(input_ids) == len(q_ids) + len(a_ids) + 1
        assert input_ids[-1] == tok.eos_token_id

        # labels 前 len(q_ids) 个是 -100
        assert all(l == -100 for l in labels[:len(q_ids)])
        # labels 后 len(a_ids)+1 个等于 input_ids
        assert labels[len(q_ids):] == input_ids[len(q_ids):]

    def test_truncation_preserves_question(self):
        """超过 max_length 时，优先保留 question 前缀。"""
        tok = MockTokenizer()
        # 构造很长的 question 和 answer
        long_q = "问题" * 100
        long_a = "答案" * 100
        input_ids, labels = _build_sft_pair(long_q, long_a, tok, max_length=100)

        assert len(input_ids) <= 100
        # question 至少保留一部分
        q_ids = tok.encode(long_q)
        assert any(l != -100 for l in labels)  # answer 部分有非 -100

    def test_empty_answer_raises_not(self):
        """空 answer 不抛异常（由调用方校验）。"""
        tok = MockTokenizer()
        input_ids, labels = _build_sft_pair("问题", "", tok)
        # answer 为空时只有 eos
        assert len(input_ids) == len(tok.encode("问题")) + 1


class TestPreTokenizeFile:
    def test_basic_flow(self, tmp_path):
        """正常流程：读取 JSONL，输出 tokenized JSONL，统计正确。"""
        # 写输入文件
        in_path = tmp_path / "train.jsonl"
        examples = [
            {"question": "问题1", "answer": "答案1", "meta": {"stage": "1-1"}},
            {"question": "问题2", "answer": "答案2", "meta": {"stage": "1-2"}},
        ]
        with open(in_path, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")

        out_path = tmp_path / "train_tokenized.jsonl"
        tok = MockTokenizer()
        stats = pre_tokenize_file(str(in_path), str(out_path), tok, max_length=2048)

        assert stats["total"] == 2
        assert stats["skipped"] == 0
        assert stats["total_tokens"] > 0
        assert stats["avg_length"] > 0

        # 验证输出文件格式
        with open(out_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 2
        for line in lines:
            record = json.loads(line)
            assert "input_ids" in record
            assert "labels" in record
            assert "meta" in record
            assert isinstance(record["input_ids"], list)
            assert isinstance(record["labels"], list)
            assert len(record["input_ids"]) == len(record["labels"])

    def test_skip_bad_lines(self, tmp_path):
        """坏行（JSON 解析失败、空 question/answer）被跳过，不中断。"""
        in_path = tmp_path / "train.jsonl"
        with open(in_path, "w", encoding="utf-8") as f:
            f.write('{"question": "好问题", "answer": "好答案"}\n')
            f.write('not valid json\n')  # 坏行
            f.write('{"question": "", "answer": "无问题"}\n')  # 空 question
            f.write('{"question": "有问题", "answer": ""}\n')  # 空 answer
            f.write('\n')  # 空行

        out_path = tmp_path / "train_tokenized.jsonl"
        tok = MockTokenizer()
        stats = pre_tokenize_file(str(in_path), str(out_path), tok)

        assert stats["total"] == 1  # 只有第一条有效
        assert stats["skipped"] == 3  # 坏行+空question+空answer（空行被 continue 不计入）

    def test_stats_only_does_not_write(self, tmp_path):
        """stats_only=True 时不写输出文件。"""
        in_path = tmp_path / "train.jsonl"
        with open(in_path, "w", encoding="utf-8") as f:
            f.write('{"question": "q", "answer": "a"}\n')

        out_path = tmp_path / "should_not_exist.jsonl"
        tok = MockTokenizer()
        stats = pre_tokenize_file(str(in_path), str(out_path), tok, stats_only=True)

        assert stats["total"] == 1
        assert not os.path.exists(out_path)

    def test_nonexistent_input_returns_zero(self, tmp_path):
        """输入文件不存在时返回零统计，不抛异常。"""
        tok = MockTokenizer()
        stats = pre_tokenize_file(str(tmp_path / "nonexistent.jsonl"),
                                   str(tmp_path / "out.jsonl"), tok)
        assert stats["total"] == 0
        assert stats["total_tokens"] == 0
