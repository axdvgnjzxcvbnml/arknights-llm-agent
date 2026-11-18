"""用支持 OpenAI Chat Completions 的本地模型重做 0-5 候选动作评测。"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from action.action_space import ActionPlan

SYSTEM = """你在玩明日方舟。根据当前战场和本步目标，从给定候选动作中选择一个。
格子代号为本题局部坐标。只返回一个 JSON 对象，字段 actions 是只含所选候选动作原文的数组，reason 是一句引用当前战场事实的简短中文理由。"""
INDEX_SYSTEM = """你在玩明日方舟。根据当前战场和本步目标，从给定候选动作中选择一个。
格子代号为本题局部坐标。只返回一个 JSON 对象，字段 choice 是所选候选的整数编号（从1开始），reason 是一句引用当前战场事实的简短中文理由。"""


def ask(case, choices, endpoint, model, mode):
    state = dict(stage="0-5", observation=case["observation"],
                 goal=case["goal"], candidates=choices)
    if mode == "index":
        state["candidates"] = dict(enumerate(choices, start=1))
    messages = [{"role": "system", "content": INDEX_SYSTEM if mode == "index" else SYSTEM},
                {"role": "user", "content": json.dumps(state, ensure_ascii=False) + "\n/no_think"}]
    body = dict(model=model, messages=messages, temperature=0, seed=42, max_tokens=256)
    req = Request(endpoint, data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=180) as response:
        return json.load(response)["choices"][0]


def grade_answer(case, choices, raw, mode):
    # Qwen 某些 chat template 在关闭思考时仍会输出一对空标签。
    answer = re.sub(r"^\s*<think>\s*</think>\s*", "", raw)
    try:
        plan = json.loads(answer)
        if mode == "index":
            index = plan["choice"]
            if type(index) is not int or not 1 <= index <= len(choices):
                raise ValueError("候选编号超出范围或类型不正确")
            plan = dict(actions=[choices[index - 1]], reason=plan["reason"])
        ActionPlan.model_validate(plan)
        if not isinstance(plan.get("reason"), str) or not plan["reason"].strip():
            raise ValueError("缺少一句理由")
        if len(plan["actions"]) != 1:
            raise ValueError("每题只能选一个动作")
    except (ValueError, KeyError, TypeError) as exc:
        return dict(valid_plan=False, accepted=False, error=str(exc))
    action = plan["actions"][0]
    if action not in case["candidates"]:
        return dict(valid_plan=True, accepted=False, error="输出动作不在候选列表中")
    index = case["candidates"].index(action) + 1
    return dict(valid_plan=True, selected=index, accepted=index in case["accepted_options"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:18179/v1/chat/completions")
    parser.add_argument("--model", default="Qwen3-1.7B")
    parser.add_argument("--mode", choices=("plan", "index"), default="plan")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads(Path(__file__).with_name("cases.json").read_text())
    # 排序扰动使用相同题目、提示和评分口径，标签始终指原始候选编号。
    with args.output.open("x", encoding="utf-8") as out:
        for order in ("original", "reversed"):
            for case in cases:
                choices = case["candidates"]
                if order == "reversed":
                    choices = list(reversed(choices))
                completion = ask(case, choices, args.endpoint, args.model, args.mode)
                raw = completion["message"].get("content") or ""
                row = dict(id=case["id"], order=order, raw=raw,
                           finish_reason=completion.get("finish_reason"),
                           **grade_answer(case, choices, raw, args.mode))
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
                print(case["id"], order, row["accepted"], flush=True)


if __name__ == "__main__":
    main()
