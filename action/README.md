# action —— 动作执行

- `adb_controller.py`：ADB 点击、拖拽、滑动接口
- `action_space.py`：动作空间定义
  - 部署：`(operator_id, grid_pos, direction)`
  - 技能：`(operator_id, skill_id)`
  - 撤退：`(operator_id)`
  - 等待：`(duration)`
- `action_executor.py`：把动作转成 ADB 命令并执行

第四批实现。mock 模式不依赖模拟器。
