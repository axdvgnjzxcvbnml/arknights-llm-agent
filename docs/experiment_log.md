# 实验记录（experiment_log）

> 用途：记录每一次可复现的实验/评估。**只记录结论与可复现信息，不粘贴任何版权数据、
> 游戏截图或权重。** 新实验按下面模板在文件顶部（最新在上）追加一节。
> 评估口径固定见 `env/reward.py`：通关 +100、漏怪 -10/点、费用溢出 -1/秒（仅评估，非 RL 训练）。

## 记录模板（复制使用）

```
## YYYY-MM-DD ｜ <实验标题>
- 分支/提交：<git rev-parse --short HEAD>
- 环境：CPU mock / V100（torch=…, cuda=…, 模型与权重路径）
- 配置：configs/*.yaml 中与本次相关的关键超参（或改动点）
- 输入/数据：语料版本（如 53 干员/52 敌人/24 关卡）、是否真实 embedding
- 指标与结果：
  - 例：通过率/胜率、平均步数、总分与明细、延迟(慢/快/桥接 ms)、检索 Top-K 命中率
- 结论：成功/失败/存疑；与上一次的差异
- 证据/产物：results/ 下报告文件名（gitignore，不入库）
- 备注/下一步：异常、待校准项（如占位坐标、真实波次时间轴）
```

---

## 2026-09-24 ｜ Mock 闭环基线（CPU，第八批起点）

- 分支/提交：`e9e990c`（第七批；API 快照远端 HEAD `b6b7591`，内容 blob 一致）
- 环境：CPU 沙箱（Python 3.12，torch 2.14+cpu，无 CUDA）；**全部为 mock 组件**
- 输入/数据：PRTS 语料 53 干员 / 52 敌人 / 24 关卡（本地，gitignore）；RAG 真实 bge-small-zh（923 chunk）
- 指标与结果（mock，非真机性能）：
  - 三段冒烟全绿：视觉 15/15、Agent 14/14、环境 14/14；`run_smoke.sh` 通过
  - 全量单测 146 通过（1 个真机用例 skip）；68 个 .py 过 py3.8 语法检查
  - mock 对局：win=10 步通关总分 +100（无漏怪/无溢出）；lose=3 步生命归零漏 3 点总分 -30
- 结论：CPU 侧模块契约与接口闭环正确；数值为脚本化 mock，不代表模型/真机表现
- 证据/产物：`results/episode_report_win.txt`、`results/episode_report_lose.txt`、
  `results/agent_decision_log.txt`、`results/perception_smoke_report.txt`（均 gitignore）
- 备注/下一步：占位坐标与真实波次时间轴待真机校准；真实模型与真机评估见 V100 待办。

---

<!-- 新实验记录追加在本注释上方（最新在上）。 -->
