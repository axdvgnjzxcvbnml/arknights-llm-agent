#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 web-kb 的 mock 接口夹具（API 形状，**直接复用后端真实代码**）。

为什么这样设计：
- mock_src/ 下是**虚构内容**（无 PRTS 版权文本），但 JSON 结构严格对齐真实爬虫产物
  （trait 单数 / skills.levels[].level / 顶层 enemies / 级别"0"+地位 / 作战消耗）。
- 本脚本把后端当"唯一事实来源"：用真实 knowledge.graph.build_graph 建图、真实
  NetworkXGraphProvider 出 subgraph/node、真实 KnowledgeService+MCP 工具出
  operator/stage/recommend，再 model_dump(by_alias=True) 落盘。
  → 前端 mock 模式与真实模式拿到的 JSON **形状一致、克制规则一致**，
    C1~C5 那种前端复刻漂移被彻底消除（前端不再自己算规则）。
- 每个夹具还用 knowledge.mcp_tools.schemas 的 Pydantic 模型反查校验，形状不符即报错。

用法（仓库根）：python web-kb/scripts/gen_mock.py
输出：web-kb/public/mock/**（随前端提交，内容为虚构示例）。
"""

import copy
import glob
import json
import os
import shutil
import sys

# ---- 路径：仓库根入 sys.path（web-kb/scripts 在 web-kb 下两级）----
HERE = os.path.dirname(os.path.abspath(__file__))
WEBKIT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(WEBKIT)
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

import yaml  # noqa: E402

from api.server import NetworkXGraphProvider  # noqa: E402
from knowledge.graph.build_graph import build_graph  # noqa: E402
from knowledge.mcp_tools import (schemas as S, tools_operator, tools_stage)  # noqa: E402
from knowledge.mcp_tools.service import KnowledgeService  # noqa: E402
from knowledge.rag.config import load_knowledge_config  # noqa: E402

MOCK_SRC = os.path.join(WEBKIT, "mock_src")
OUT = os.path.join(WEBKIT, "public", "mock")
BUILD = os.path.join(WEBKIT, ".mockbuild")

FEATURED_STAGES = ["3-8", "1-7"]


def _write(rel, obj):
    path = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def _dump(model):
    """与 api.server 完全一致的序列化口径。"""
    return model.model_dump(by_alias=True)


def make_temp_config():
    """复制真实 knowledge.yaml，仅把数据/图谱目录指向 mock_src 与临时构建目录。"""
    cfg = load_knowledge_config(os.path.join(REPO_ROOT, "configs", "knowledge.yaml"))
    cfg = copy.deepcopy(cfg)
    cfg["rag"]["build"]["raw_dir"] = MOCK_SRC
    gdir = os.path.join(BUILD, "graph")
    cfg["graph"]["output_dir"] = gdir
    cfg["graph"]["graphml_file"] = "mock_graph.graphml"
    cfg["rag"]["vector_store"]["persist_dir"] = os.path.join(BUILD, "vector_store")
    os.makedirs(gdir, exist_ok=True)
    path = os.path.join(BUILD, "knowledge.yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    return cfg, path


def load_src(subdir):
    out = []
    for p in sorted(glob.glob(os.path.join(MOCK_SRC, subdir, "*.json"))):
        with open(p, encoding="utf-8") as f:
            out.append((os.path.splitext(os.path.basename(p))[0], json.load(f)))
    return out


def build_search_corpus():
    """用 mock_src 合成 GuideHit 形状的检索语料（score=0，由前端本地打分排序）。

    与真实 /api/search 一致：命中一律 evidence=retrieved（检索到的参考资料，非事实）。
    """
    hits = []

    def add(content, source, doc_type, section, url_title):
        hit = S.GuideHit(content=content, score=0.0, source=source,
                         doc_type=doc_type, section=section,
                         url=S.PRTS_WIKI_BASE + url_title)
        hits.append(hit.model_dump(by_alias=True))

    for page, d in load_src("operators"):
        meta, trait = d.get("meta", {}), d.get("trait", {}) or {}
        add("%s（%s）%s星%s，分支：%s。位置：%s，标签：%s。特性：%s。"
            % (page, meta.get("nameEn", ""), meta.get("star_rating", "?"),
               meta.get("class", ""), meta.get("branch", ""), meta.get("pos", "-"),
               meta.get("tag", "-"), trait.get("描述", "-")),
            page, "operator", "meta", page)
        attrs = d.get("extra_attrs", {}) or {}
        add("%s基础属性：再部署%s，费用%s，阻挡%s，攻击间隔%s。"
            % (page, attrs.get("再部署时间", "-"), attrs.get("初始部署费用", "-"),
               attrs.get("阻挡数", "-"), attrs.get("攻击间隔", "-")),
            page, "operator", "attrs", page)
        for sk in d.get("skills", []) or []:
            levels = sk.get("levels", []) or []
            lv7 = next((x for x in levels if x.get("level") == "7"),
                       levels[0] if levels else {})
            add("%s技能「%s」（%s）：%s。初始%s，消耗%s，持续%s。"
                % (page, sk.get("name", ""), sk.get("type", ""), lv7.get("desc", ""),
                   lv7.get("initial", "-"), lv7.get("cost", "-"), lv7.get("duration", "-")),
            page, "operator", "技能/%s" % sk.get("name", ""), page)

    for page, d in load_src("enemies"):
        data = (d.get("levels") or [{}])[-1].get("data", {})
        add("%s：%s。生命%s，攻击%s，防御%s，法抗%s，移速%s。%s"
            % (page, data.get("地位", ""), data.get("最大生命值", "-"),
               data.get("攻击力", "-"), data.get("防御力", "-"),
               data.get("法术抗性", "-"), data.get("移动速度", "-"),
               data.get("描述", "")),
            page, "enemy", "level0", page)

    for page, d in load_src("stages"):
        code, normal = d.get("code", ""), d.get("normal", {}) or {}
        rows = "、".join("%s×%s" % (r.get("名称"), r.get("数量"))
                        for r in d.get("enemies", []) or [])
        add("关卡%s「%s」，推荐等级%s，作战消耗%s。敌情：%s。"
            % (code, normal.get("name", ""), normal.get("推荐等级", "-"),
               normal.get("作战消耗", "-"), rows),
            page, "stage", "enemies", code)

    guides_path = os.path.join(MOCK_SRC, "guides", "guides.json")
    if os.path.isfile(guides_path):
        for g in json.load(open(guides_path, encoding="utf-8")):
            add("【%s】%s" % (g.get("title", ""), g.get("text", "")),
                g.get("title", ""), "guide", g.get("stage", ""), g.get("title", ""))

    # 反查校验：每条都能被 GuideHit 接受（字段名/类型）
    for h in hits:
        S.GuideHit(**h)

    return {
        "found": True, "query": "", "evidence": S.EVIDENCE_RETRIEVED,
        "embedding_backend": "mock",
        "note": S.GuideOut(found=True).note,
        "hits": hits,
    }


def main():
    # 清理旧夹具（旧版 prts_raw 自造 schema 整体废弃）
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(BUILD, exist_ok=True)

    cfg, cfg_path = make_temp_config()

    # 1) 真实建图（规则、阈值全部来自后端 configs/knowledge.yaml）
    stats = build_graph(cfg)
    print("[gen] 建图完成：节点 %s 边 %s"
          % (stats["nodes"]["total"], stats["edges"]["total"]))

    provider = NetworkXGraphProvider(config_path=cfg_path)
    svc = KnowledgeService(config_path=cfg_path)

    # 2) 干员 OperatorOut + 节点邻居（NodeDetail）
    operator_pages = [p for p, _ in load_src("operators")]
    catalog_ops = []
    for page in operator_pages:
        out = tools_operator.query_operator(page, service=svc)
        assert out.found, "干员夹具生成失败：%s" % page
        _write("operator/%s.json" % page, _dump(out))
        node = provider.node("operator:%s" % page)
        assert node is not None, "节点缺失：operator:%s" % page
        _write("node/operator_%s.json" % page, node)
        catalog_ops.append({"name": out.display_name or page,
                            "class": out.operator_class, "star": out.star_rating})

    # 3) 关卡 StageOut + 子图 + 推荐
    catalog_stages = []
    for code in FEATURED_STAGES:
        st = tools_stage.query_stage(code, service=svc)
        assert st.found, "关卡夹具生成失败：%s" % code
        _write("stage/%s.json" % code, _dump(st))
        S.StageOut(**_dump(st))  # 反查校验（by_alias 往返）

        sub = provider.stage_subgraph(code)
        assert sub is not None and sub["found"], "子图缺失：%s" % code
        _write("subgraph/%s.json" % code, sub)

        rec = tools_stage.recommend_operators(code, service=svc)
        _write("recommend/%s.json" % code, _dump(rec))
        S.RecommendOut(**_dump(rec))
        catalog_stages.append({"stage_id": code, "title": sub["stage_title"]})

    # 4) overview（页面规模统计用）
    _write("overview.json", provider.overview())

    # 5) 检索语料（GuideHit 形状）
    _write("search_corpus.json", build_search_corpus())

    # 6) 目录（供前端选择器；真实模式下前端改用内置 FEATURED 常量）
    _write("catalog.json", {"operators": catalog_ops, "stages": catalog_stages})

    print("[gen] 夹具输出目录：%s" % OUT)
    print("[gen] 干员 %d，关卡 %d" % (len(catalog_ops), len(catalog_stages)))
    print("[gen] 全部夹具已通过 Pydantic 形状校验")


if __name__ == "__main__":
    main()
