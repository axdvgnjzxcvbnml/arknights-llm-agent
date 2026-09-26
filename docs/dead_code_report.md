# 死代码检测报告

> 检测时间：2026-09-27
> 工具：ruff（F401 未使用 import / F841 未使用变量 / F842 未使用循环变量）
> 范围：agent/ knowledge/ perception/ action/ env/ api/ training/ strategy/ video_extract/ scripts/
> 排除：tests/ frontend/ web-kb/ data/ weights/ results/

## 检测结果总览

| 类别 | 检测数 | 已修复 | 保留（误报/有意） |
| --- | --- | --- | --- |
| F401 未使用 import | 72 | 72（ruff 自动修复） | 0 |
| F841 未使用变量 | 2 | 2（手动删除） | 0 |
| F842 未使用循环变量 | 0 | 0 | 0 |
| **合计** | **74** | **74** | **0** |

## 已修复详情

### F401 未使用 import（72 处，ruff --fix 自动处理）

分布在 20+ 个文件，主要类型：
- `typing.List` / `typing.Dict` / `typing.Optional` 等类型注解导入后未使用（代码已改用 `from __future__ import annotations` 或内联类型）
- 模块内导入的类/函数未使用（重构后残留）
- `os` / `sys` / `json` / `time` 等标准库导入后未使用

**修复方式**：`ruff check --select F401 --fix`，自动删除未使用的 import 语句。

**验证**：修复后跑冒烟测试 + 148 个核心单元测试，全部通过，无回归。

### F841 未使用变量（2 处，手动删除）

| 文件 | 行号 | 变量 | 修复方式 |
| --- | --- | --- | --- |
| `training/maa_job_downloader.py` | 290 | `id_item` | 删除赋值（dict comprehension 结果未被后续代码引用） |
| `training/pre_tokenize.py` | 252 | `result` | 改为不赋值（main 函数调用后不需要返回值） |

## 误报说明

ruff 的 F401/F841 在本项目中**零误报**，原因：
1. Pydantic 模型字段通过 `Field()` 定义，不会被标记为未使用
2. `__all__` 导出的符号 ruff 会自动识别，不会误报
3. MCP 工具注册通过装饰器/函数名注册，ruff 能识别调用链

## 工具局限

1. **vulture 未使用**：沙箱未安装 vulture，且 ruff 的 F 规则已覆盖主要死代码场景。vulture 能检测未使用的函数/类，但误报率较高（回调函数、动态调用、Pydantic 模型方法等），人工复核成本高。
2. **前端死代码未检测**：frontend/ 和 web-kb/ 的 TypeScript/TSX 死代码需用 eslint（`no-unused-vars`）检测，本次未覆盖。
3. **动态导入**：`importlib.import_module()` 等动态导入无法被静态分析检测。

## 后续建议

1. **CI 集成 ruff**：在 `.github/workflows/ci.yml` 加一个 `ruff-check` job，跑 `ruff check --select F401,F841 .`，防止新死代码引入。
2. **前端 eslint**：frontend/ 配置 eslint + `no-unused-vars` 规则。
3. **定期全量扫描**：每批开发结束时跑一次 `ruff check .`，保持代码整洁。
