"""RAG 检索相关性测试：5 条指定 query，验证 Top-K 是否命中预期 chunk。

用法：
    python -m knowledge.rag.retrieval_test                 # 打印每条 query 的 Top-K
    python -m knowledge.rag.retrieval_test --json out.json # 同时落机器可读结果

判定方式（基于元数据与文本，不依赖人工）：
1. 能天使的技能是什么   -> Top-K 中存在 source=能天使、section 以 skill 开头
2. 3-8 有哪些敌人       -> Top-K 中存在 3-8 关卡、section=enemies
3. 碎骨的属性           -> Top-K 中存在 source=碎骨、type=enemy
4. 先锋干员的费用       -> Top-K 中存在 type=operator 且文本含"先锋"和"部署费用"
5. 沉默效果是什么       -> Top-K 中存在文本含"沉默"的 chunk
"""

import argparse
import json

from .config import DEFAULT_CONFIG_PATH, load_knowledge_config
from .retriever import Retriever

__all__ = ["TEST_QUERIES", "run_tests"]

TEST_QUERIES = [
    {"query": "能天使的技能是什么", "expect": "能天使 skill chunk",
     "match": lambda r: r["metadata"].get("source") == "能天使"
                        and r["metadata"].get("section", "").startswith("skill")},
    {"query": "3-8 有哪些敌人", "expect": "3-8 stage enemies chunk",
     "match": lambda r: r["metadata"].get("source", "").startswith("3-8")
                        and r["metadata"].get("section") == "enemies"},
    {"query": "碎骨的属性", "expect": "碎骨 enemy chunk",
     "match": lambda r: r["metadata"].get("source") == "碎骨"
                        and r["metadata"].get("type") == "enemy"},
    {"query": "先锋干员的费用", "expect": "vanguard operator chunk mentioning 部署费用",
     "match": lambda r: r["metadata"].get("type") == "operator"
                        and "先锋" in r["content"] and "部署费用" in r["content"]},
    {"query": "沉默效果是什么", "expect": "chunk mentioning 沉默",
     "match": lambda r: "沉默" in r["content"]},
]


def run_tests(config=None, k=5):
    # type: (dict, int) -> dict
    retriever = Retriever(config=config)
    print("embedding backend: %s" % retriever.embedder.backend)
    print("collection count: %d\n" % retriever.store.count())
    if retriever.embedder.backend == "mock":
        print("WARN: 当前为 mock embedding（伪随机向量），本测试仅验证接口，不验证相关性\n")
    report = {"backend": retriever.embedder.backend, "cases": []}
    pass_n = 0
    for case in TEST_QUERIES:
        results = retriever.search(case["query"], k=k)
        hit_idx = None
        for i, r in enumerate(results):
            if case["match"](r):
                hit_idx = i
                break
        ok = hit_idx is not None
        pass_n += int(ok)
        top = results[0] if results else None
        print("Q: %s" % case["query"])
        print("   期望: %s" % case["expect"])
        if top:
            print("   Top1: [score=%s] (%s/%s/%s) %s" % (
                top["score"], top["metadata"].get("source"),
                top["metadata"].get("type"), top["metadata"].get("section"),
                top["content"].replace("\n", " ")[:80]))
        print("   结果: %s\n" % ("HIT@%d (第%d条)" % (k, hit_idx + 1) if ok else "MISS"))
        report["cases"].append({
            "query": case["query"],
            "expect": case["expect"],
            "hit": ok,
            "hit_rank": (hit_idx + 1) if hit_idx is not None else None,
            "top_k": [
                {"score": r["score"], "source": r["metadata"].get("source"),
                 "type": r["metadata"].get("type"),
                 "section": r["metadata"].get("section"),
                 "snippet": r["content"].replace("\n", " ")[:120]}
                for r in results
            ],
        })
    report["pass"] = pass_n
    report["total"] = len(TEST_QUERIES)
    print("汇总: %d/%d 命中" % (pass_n, len(TEST_QUERIES)))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="RAG 检索相关性测试")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--json", dest="json_path", default=None, help="结果写入 JSON")
    args = parser.parse_args(argv)
    config = load_knowledge_config(args.config)
    report = run_tests(config=config, k=args.k)
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print("结果已写入 %s" % args.json_path)
    # mock backend 下不判失败（接口测试）；真实 embedding 下未全部命中则退出码 1
    if report["backend"] != "mock" and report["pass"] != report["total"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
