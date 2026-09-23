"""从 data/prts_raw/ 的 JSON 构建 ChromaDB 向量库。

切分策略（按类型区分，200-500 字/chunk，按段落/句子边界切分，不硬切语义）：
- operator（干员）：meta（含费用等基础属性）/ trait 特性 / obtain 获得方式 /
                    attrs 成长属性 / 每个技能各自成 chunk（过长再按句切分）
- enemy（敌人）：每个级别（level0/1/2）一个 chunk，含地位、种类、属性、特性
- stage（关卡）：info 信息卡 / enemies 敌方情报，两个 chunk
- guide（攻略文本）：parse_guides 生成的文本块，按段落打包切分

每个 chunk 元数据：source（页面名）、type、section、url。
写入使用 upsert + 确定性 id，重复构建不会产生重复文档。

CLI:
    python -m knowledge.rag.build_rag                 # 增量构建（upsert）
    python -m knowledge.rag.build_rag --rebuild       # 清空 collection 后重建
    python -m knowledge.rag.build_rag --config configs/knowledge.yaml
"""

import argparse
import glob
import hashlib
import json
import os
import re
import urllib.parse

from ..crawler.parse_guides import (
    enemy_to_guide,
    operator_to_guide,
    stage_to_guide,
)
from .config import DEFAULT_CONFIG_PATH, load_knowledge_config
from .embedding import load_embedder
from .vector_store import KnowledgeStore

__all__ = ["build_all", "chunk_operator", "chunk_enemy", "chunk_stage"]

PRTS_WIKI_BASE = "https://prts.wiki/w/"
UPSERT_BATCH = 256

# 属性表中过长的阶段名（"精英0 1级 不包括 信赖 及 潜能 加成"）压缩展示
_STAGE_SHORT = re.compile(r"(精英\d+ (?:\d+级|满级))")
_SENT_SPLIT = re.compile(r"(?<=[。；！？?!\n])")


# ---------------- 通用切分工具 ----------------

def _split_sentences(text):
    # type: (str) -> list
    """按中文句读/换行切句（保留标点），不切断语义。"""
    parts = [p.strip() for p in _SENT_SPLIT.split(text)]
    return [p for p in parts if p]


def _pack_paragraphs(paragraphs, max_chars):
    # type: (list, int) -> list
    """把若干段落贪心打包成 <=max_chars 的文本块；单句超长才按句再切。

    200 字是目标下限而非硬下限（如"获得方式"天然很短），不做无意义填充。
    """
    chunks = []
    buf = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chars:
            if buf and len(buf) + 1 + len(para) > max_chars:
                chunks.append(buf)
                buf = para
            else:
                buf = (buf + "\n" + para) if buf else para
        else:
            # 段落本身超长：先把缓冲落盘，再按句子切
            if buf:
                chunks.append(buf)
                buf = ""
            sent_buf = ""
            for sent in _split_sentences(para):
                # 极端情况下单句仍超长，按 max_chars 硬切（最后兜底）
                if len(sent) > max_chars:
                    if sent_buf:
                        chunks.append(sent_buf)
                        sent_buf = ""
                    for i in range(0, len(sent), max_chars):
                        chunks.append(sent[i:i + max_chars])
                    continue
                if sent_buf and len(sent_buf) + len(sent) > max_chars:
                    chunks.append(sent_buf)
                    sent_buf = sent
                else:
                    sent_buf += sent
            if sent_buf:
                chunks.append(sent_buf)
    if buf:
        chunks.append(buf)
    return chunks


def _chunk_id(doc_type, source, section, index):
    # type: (str, str, str, int) -> str
    raw = "|".join([doc_type, source, section, str(index)])
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _page_url(title):
    # type: (str) -> str
    return PRTS_WIKI_BASE + urllib.parse.quote(title, safe="")


def _make_chunks(doc_type, source, section, url, paragraphs, max_chars, context=None):
    # type: (str, str, str, str, list, int, str) -> list
    # context 会被重复前缀到续块，打包时预留其长度，保证加完仍不超 max_chars
    eff_max = max(100, max_chars - len(context)) if context else max_chars
    texts = _pack_paragraphs(paragraphs, eff_max)
    out = []
    for i, text in enumerate(texts):
        # 多块内容的续块重复简短上下文（干员名/技能名），保证每块可独立检索
        if i > 0 and context and not text.startswith(context):
            text = context + text
        out.append({
            "id": _chunk_id(doc_type, source, section, i),
            "text": text.strip(),
            "metadata": {
                "source": source,
                "type": doc_type,
                "section": section,
                "url": url,
            },
        })
    return out


def _stage_title(stem, data):
    # type: (str, dict) -> str
    """关卡页标题：样本期文件名可能是"3-8"（缺名称），用 code+name 还原"3-8 黄昏"。"""
    if " " in stem:
        return stem
    code = data.get("code") or stem
    name = data.get("normal", {}).get("name", "")
    return ("%s %s" % (code, name)).strip() if name else stem


# ---------------- 干员切分 ----------------

def _kv_line(key, value):
    # type: (str, object) -> str
    if value is None or value == "":
        return ""
    return "%s：%s" % (key, value)


def chunk_operator(data, max_chars=500, source=None):
    # type: (dict, int, str) -> list
    # 实体身份以页面标题（文件名）为准；消歧义形态（如"阿米娅(近卫)"）必须区分
    source = source or data.get("name") or data.get("meta", {}).get("name") or ""
    url = _page_url(source)
    meta = data.get("meta", {})
    chunks = []

    # meta：星级/职业/分支/位置/标签 + 再部署/费用/阻挡/攻击间隔等战斗关键属性
    meta_paras = []
    head = "%s星%s干员%s，分支%s，%s，标签：%s。" % (
        meta.get("star_rating", "?"), meta.get("class", ""), source,
        meta.get("branch", ""), meta.get("pos", ""), meta.get("tag", ""),
    )
    if meta.get("group"):
        head += "所属势力：%s。" % meta["group"]
    meta_paras.append(head)
    extra = data.get("extra_attrs", {}) or {}
    for key in ("初始部署费用", "阻挡数", "再部署时间", "攻击间隔"):
        line = _kv_line(key, extra.get(key))
        if line:
            meta_paras.append(line)
    chunks += _make_chunks("operator", source, "meta", url, meta_paras, max_chars)

    # 特性
    trait = data.get("trait", {}) or {}
    trait_paras = []
    for key, value in trait.items():
        line = _kv_line(key, value)
        if line:
            trait_paras.append("干员%s的%s" % (source, line) if key == "描述" else line)
    if trait_paras:
        chunks += _make_chunks("operator", source, "trait", url, trait_paras, max_chars)

    # 获得方式
    obtain = data.get("obtain", {}) or {}
    obtain_paras = [_kv_line(k, v) for k, v in obtain.items() if v]
    if obtain_paras:
        chunks += _make_chunks("operator", source, "obtain", url,
                               ["干员%s的获得信息。" % source] + obtain_paras, max_chars)

    # 成长属性（精英阶段 × 生命/攻击/防御/法抗）
    growth = data.get("growth_attrs", {}) or {}
    stages = growth.get("stages", []) or []
    rows = growth.get("rows", {}) or {}
    if stages and rows:
        short_stages = []
        for s in stages:
            m = _STAGE_SHORT.search(s or "")
            short_stages.append(m.group(1).replace(" ", "") if m else s)
        g_paras = ["干员%s在各精英阶段的属性（%s）。" % (source, " / ".join(short_stages))]
        for attr, values in rows.items():
            g_paras.append("%s：%s" % (attr, " / ".join(str(v) for v in values)))
        chunks += _make_chunks("operator", source, "attrs", url, g_paras, max_chars)

    # 技能：每个技能独立成 chunk（10 级数据过长时按句/行打包成多块）
    for skill in data.get("skills", []) or []:
        sname = skill.get("name", "未知技能")
        paras = ["干员%s的技能「%s」，技力机制：%s。" % (source, sname, skill.get("type", ""))]
        for lv in skill.get("levels", []) or []:
            parts = ["等级%s：%s" % (lv.get("level", "?"), lv.get("desc", ""))]
            tail = []
            if lv.get("initial") not in (None, ""):
                tail.append("初始技力%s" % lv["initial"])
            if lv.get("cost") not in (None, ""):
                tail.append("消耗%s" % lv["cost"])
            if lv.get("duration") not in (None, ""):
                tail.append("持续%s" % lv["duration"])
            if tail:
                parts.append("（%s）" % "，".join(tail))
            paras.append("".join(parts))
        chunks += _make_chunks(
            "operator", source, "skill:%s" % sname, url, paras, max_chars,
            context="干员%s的技能「%s」（续）。" % (source, sname),
        )

    return chunks


# ---------------- 敌人切分 ----------------

_ENEMY_FIELDS = (
    "地位", "种类", "描述", "攻击方式", "行动方式", "最大生命值", "攻击力",
    "防御力", "法术抗性", "攻击半径", "重量", "移动速度", "攻击间隔",
    "生命自回速度", "元素抗性", "损伤抵抗", "异常抗性", "基础嘲讽等级", "目标价值",
)


def chunk_enemy(data, max_chars=500, source=None):
    # type: (dict, int, str) -> list
    source = source or data.get("name") or ""
    url = _page_url(source)
    chunks = []
    for lv in data.get("levels", []) or []:
        d = lv.get("data", {}) or {}
        level = lv.get("level", 0)
        name = d.get("名称", source)
        paras = ["敌人%s（级别%s）。" % (name, level)]
        for key in _ENEMY_FIELDS:
            line = _kv_line(key, d.get(key))
            if line:
                paras.append(line)
        traits = d.get("特性") or []
        if isinstance(traits, (list, tuple)):
            traits = "、".join(str(t) for t in traits if t)
        if traits:
            paras.append("特性：%s。该敌人具有%s相关机制。" % (traits, traits))
        chunks += _make_chunks(
            "enemy", source, "level%s" % level, url, paras, max_chars,
            context="敌人%s（级别%s，续）。" % (name, level),
        )
    return chunks


# ---------------- 关卡切分 ----------------

_STAGE_INFO_FIELDS = (
    "desc", "解锁条件", "推荐等级", "作战消耗", "部署上限", "初始COST",
    "COST上限", "目标点耐久", "待处理目标数量",
)
_STAGE_FIELD_CN = {
    "desc": "关卡描述",
}


def chunk_stage(data, max_chars=500, source=None):
    # type: (dict, int, str) -> list
    stem = source or data.get("name", "")
    source = _stage_title(stem, data)
    url = _page_url(source)
    code = data.get("code", source.split(" ")[0])
    normal = data.get("normal", {}) or {}
    raid = data.get("raid", {}) or {}
    chunks = []

    # 信息卡
    paras = ["关卡%s（%s）。" % (code, normal.get("name", ""))]
    for field in _STAGE_INFO_FIELDS:
        value = normal.get(field)
        line = _kv_line(_STAGE_FIELD_CN.get(field, field), value)
        if line:
            paras.append(line)
    if raid.get("name"):
        paras.append("突袭模式：%s。%s" % (raid.get("name", ""), raid.get("desc", "")))
    chunks += _make_chunks("stage", source, "info", url, paras, max_chars)

    # 敌方情报
    enemies = data.get("enemies", []) or []
    if enemies:
        e_paras = ["%s有哪些敌人？关卡%s 本关敌人配置与出场数量如下，共出场 %d 种敌人。"
                   % (code, code, len(enemies))]
        for e in enemies:
            parts = [str(e.get("名称", "未知敌人"))]
            if e.get("数量"):
                parts.append("数量%s" % e["数量"])
            if e.get("地位"):
                parts.append("地位%s" % e["地位"])
            if e.get("级别"):
                parts.append("级别%s" % e["级别"])
            for stat in ("生命值", "攻击力", "防御力", "法术抗性", "攻击间隔", "重量等级", "移动速度"):
                if e.get(stat) not in (None, ""):
                    parts.append("%s%s" % (stat, e[stat]))
            e_paras.append("，".join(parts) + "。")
        chunks += _make_chunks(
            "stage", source, "enemies", url, e_paras, max_chars,
            context="关卡%s 敌方情报（续）。" % code,
        )

    return chunks


# ---------------- 攻略文本切分 ----------------

def chunk_guide(guide, url, max_chars=500):
    # type: (dict, str, int) -> list
    title = guide.get("title", "攻略")
    text = guide.get("text", "")
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    return _make_chunks("guide", title, "guide", url, paragraphs, max_chars)


# ---------------- 构建主流程 ----------------

def _load_json_dir(subdir, raw_dir):
    # type: (str, str) -> list
    """返回 [(页面标题(文件名), data), ...]；实体身份一律以页面标题为准。"""
    out = []
    for path in sorted(glob.glob(os.path.join(raw_dir, subdir, "*.json"))):
        with open(path, "r", encoding="utf-8") as f:
            out.append((os.path.splitext(os.path.basename(path))[0], json.load(f)))
    return out


def build_all(config, rebuild=False):
    # type: (dict, bool) -> dict
    rag_cfg = config["rag"]
    raw_dir = rag_cfg["build"]["raw_dir"]
    max_chars = int(rag_cfg["build"].get("chunk_max_chars", 500))
    include_guides = bool(rag_cfg["build"].get("include_guides", True))

    operators = _load_json_dir("operators", raw_dir)
    enemies = _load_json_dir("enemies", raw_dir)
    stages = _load_json_dir("stages", raw_dir)
    print("[build] 读取 JSON：干员 %d，敌人 %d，关卡 %d"
          % (len(operators), len(enemies), len(stages)))

    all_chunks = []
    for stem, data in operators:
        all_chunks += chunk_operator(data, max_chars, source=stem)
    for stem, data in enemies:
        all_chunks += chunk_enemy(data, max_chars, source=stem)
    for stem, data in stages:
        all_chunks += chunk_stage(data, max_chars, source=stem)

    # 攻略文本：逐实体生成（chunk source 用页面标题，消歧义形态不撞 id）
    if include_guides:
        for stem, data in operators:
            guide = operator_to_guide(data)
            guide["title"] = "干员攻略_%s" % stem
            all_chunks += chunk_guide(guide, _page_url(stem), max_chars)
        for stem, data in enemies:
            guide = enemy_to_guide(data)
            guide["title"] = "敌人攻略_%s" % stem
            all_chunks += chunk_guide(guide, _page_url(stem), max_chars)
        for stem, data in stages:
            source = _stage_title(stem, data)
            guide = stage_to_guide(data)
            guide["title"] = "关卡攻略_%s" % source
            all_chunks += chunk_guide(guide, _page_url(source), max_chars)

    if not all_chunks:
        raise RuntimeError("未生成任何 chunk，请检查 %s 下是否有已解析 JSON" % raw_dir)

    # chunk 长度统计
    lengths = sorted(len(c["text"]) for c in all_chunks)
    over = [c for c in all_chunks if len(c["text"]) > max_chars]
    print("[build] 生成 chunk %d 个；长度 min/中位/max = %d/%d/%d；超 %d 字的 %d 个"
          % (len(all_chunks), lengths[0], lengths[len(lengths) // 2], lengths[-1],
             max_chars, len(over)))

    # 向量化 + 入库
    embedder = load_embedder(rag_cfg.get("embedding", {}))
    print("[build] embedding backend = %s, dim = %d" % (embedder.backend, embedder.dim))
    vs_cfg = rag_cfg["vector_store"]
    store = KnowledgeStore(
        persist_dir=vs_cfg["persist_dir"],
        collection=vs_cfg["collection"],
        distance=vs_cfg.get("distance", "cosine"),
    )
    if rebuild:
        store.reset_collection()
        print("[build] 已清空旧 collection")

    texts = [c["text"] for c in all_chunks]
    metadatas = [c["metadata"] for c in all_chunks]
    ids = [c["id"] for c in all_chunks]
    vectors = []
    for start in range(0, len(texts), int(rag_cfg.get("embedding", {}).get("batch_size", 32))):
        vectors += embedder.encode(texts[start:start + 32])
    assert len(vectors) == len(texts), "向量数量与 chunk 数量不一致"

    for start in range(0, len(ids), UPSERT_BATCH):
        end = start + UPSERT_BATCH
        store.upsert(ids[start:end], vectors[start:end],
                     texts[start:end], metadatas[start:end])

    stats = {
        "documents": {"operator": len(operators), "enemy": len(enemies), "stage": len(stages)},
        "chunks_total": len(all_chunks),
        "embedder_backend": embedder.backend,
        "collection_count": store.count(),
    }
    by_section = {}
    for c in all_chunks:
        t = c["metadata"]["type"]
        by_section[t] = by_section.get(t, 0) + 1
    stats["chunks_by_type"] = by_section
    print("[build] 完成：%s" % json.dumps(stats, ensure_ascii=False))
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description="从 PRTS JSON 构建 RAG 向量库")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--rebuild", action="store_true", help="清空 collection 后重建")
    args = parser.parse_args(argv)
    config = load_knowledge_config(args.config)
    build_all(config, rebuild=args.rebuild)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
