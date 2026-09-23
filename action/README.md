# action —— 动作执行

把 Agent 的高层决策动作编译成底层 ADB 原语并下发到 MuMu 模拟器。**本模块的 ADB 封装为
自写轻量实现，不使用 maa-framework 或其 Python 绑定，因此项目保持 MIT 许可。**

## 文件

| 文件 | 职责 |
|---|---|
| `adb_controller.py` | `ADBController`（connect / tap / swipe / key / screencap_png，面向 MuMu `127.0.0.1:7555`）+ `MockADBController`（只记录不执行）+ `OpResult` |
| `action_space.py` | Pydantic 动作契约 `Action` / 序列 `ActionPlan` / 结果 `ActionResult·PlanResult` + `GridConverter`（格子/卡槽→像素） |
| `action_executor.py` | `ActionExecutor`（动作→tap/swipe/wait 原语，顺序执行、单步失败不中断）+ `MockActionExecutor`（CPU 闭环） |
| `config.py` | 加载 `configs/action.yaml`，并合并 `configs/perception.yaml` 的 `coords`（坐标单一来源） |

## 动作空间（与第五批 `agent/output_schema.py` 对齐）

| action | 必需字段 | 说明 |
|---|---|---|
| `deploy` | `operator_id, grid_pos, direction(up/down/left/right)` | 部署干员到格子并定朝向 |
| `skill` | `operator_id, skill_id(1-3)` | 开技能 |
| `retreat` | `operator_id` | 撤退已部署干员 |
| `wait` | `duration_ms(0-60000)` | 等待 |

非法字段组合（缺字段/越界/多余字段）由 Pydantic 在构造时直接报错。一次决策可用
`ActionPlan(actions=[...])` 批量下发；执行器逐个执行，**单个动作失败只记录原因、中止
该动作，不中断整段序列**（`PlanResult.failed/succeeded/completed`）。

## 干员定位（resolver，不臆造坐标）

动作里只有 `operator_id`，其底部卡槽位 / 已部署格子来自当前视觉状态，由两个 resolver 注入：

- `card_slot_resolver(operator_id) -> 卡槽序号(0起) | None`
- `deployed_cell_resolver(operator_id) -> 格子名(如 'E4') | None`

返回 None 时部署/撤退会得到带明确原因的失败结果，而不是乱点。

## MAA 复用边界（许可）

- **未 vendoring、未运行时解析、未打包** MaaAssistantArknights 的任何代码/坐标/模板资源。
- ADB 命令与接口思路参考 MAA，但全部自己实现（connect / `input tap` / `input swipe` /
  `exec-out screencap`），覆盖自动战斗常用操作。
- UI 坐标均为 `configs/perception.yaml` 与 `configs/action.yaml` 中的**占位值**，真机阶段
  由使用者**自行测量或参考 MAA 后重写**填入本地配置；技能就绪等模板图片由使用者自行从
  [MaaAssistantArknights](https://github.com/MaaAssistantArknights/MaaAssistantArknights)
  获取并本地接入（谨致谢忱）。这样本仓库不含其 AGPL 内容，保持 MIT。
- 真机手势亦为占位（部署="点卡牌→朝方向滑"、撤退="点干员→点撤退按钮"、技能直接点技能键），
  代码中以 `TODO 真机校准` 标注，上线前需按真实 UI 校准（含等距地图的斜切坐标）。

## 快速验证（CPU，无设备）

```bash
python -m pytest tests/test_action.py -q        # 契约/边界恒跑，真实设备用例自动 skip
bash scripts/run_smoke.sh                       # 末尾 [7/7] 即 mock 动作编排
```
