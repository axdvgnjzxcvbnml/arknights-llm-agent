# env —— 环境封装

把「看 → 想/给动作 → 做 → 再看」封装成统一接口，让 CPU 沙箱跑 mock 闭环、V100 上线后
直接接真实模拟器。**它是调度层，不是 RL 的 Gym：不产生梯度、不用于训练**，只负责调度
感知/决策/执行并记录对局。

## 文件

| 文件 | 职责 |
|---|---|
| `arknights_env.py` | `ArknightsEnv`：Gym 风格 `reset/step/get_state/is_done/get_log/close` + `run_episode`（注入 Agent 组件时自动跑）+ `EnvStep/EpisodeLog` + `render_episode_report` |
| `mock_env.py` | `ScriptedPerception`（叠加通关/生命归零终局）+ `build_mock_env/run_mock_episode`：10 步通关 / 3 步失败两局 |
| `reward.py` | 评估奖励 `EpisodeReward/RewardBreakdown`（**仅评估，非训练**） |

## 依赖注入

三大块经构造函数注入，mock/真实可互换，环境代码不改：

- `perception`：`perceive(elapsed)→{frame,state,analysis,state_text}`、
  `on_after_step(plan, result)`，可选 `regen()/is_cleared()`；
- `executor`：`execute(ActionPlan)→PlanResult`（action 包）；
- 可选 Agent 组件 `knowledge/slow/bridge/fast`：提供后可用 `run_episode()` 自动对局。

`step(action)` 的 action 接受 `Action / ActionPlan / FastCommand / List[Action]`
（`coerce_plan` 归一化），返回 `(next_state, step_reward, done, info)`。

## 结束判定

生命 `life_points<=0` → `defeat`；`perception.is_cleared()` 为真 → `win`；
到达 `max_steps` 仍未结束 → `timeout`；外部 `close()` → `aborted`。

## 评估奖励（reward.py，非训练）

- 通关 **+100**；目标耐久每掉 1 点（漏怪）**-10**；费用打满上限持续 **-1/秒**（按真实 dt）。
逐帧 `observe(state, dt_sec)` 累计，`finalize(outcome)` 汇总 `RewardBreakdown`
（各项分/总分/起止耐久/漏怪点数/溢出秒数/逐条明细）。权重由 `RewardConfig` 注入。

## 对局报告

`render_episode_report(log)` 输出每步的费用/耐久、决策结论与依据、证据、动作执行结果、
本步奖励与耗时，末尾汇总奖励明细；冒烟落盘到
`results/episode_report_win.txt`、`results/episode_report_lose.txt`（results 已 gitignore）。

## 快速验证（CPU）

```bash
python -m pytest tests/test_env.py -q   # 奖励/接口/两局脚本/import 轻量
bash scripts/run_smoke.sh               # 第 3 段：reset->step->is_done 完整两局
```

```python
from env.mock_env import run_mock_episode
win  = run_mock_episode("win",  win_in=10)   # outcome=win,  总分 +100
lose = run_mock_episode("lose", lose_in=3)   # outcome=defeat, 漏3点 总分 -30
```
