# 日志与可观测性规范

> 生效时间：2026-09-27
> 范围：全仓库 Python 代码

## 一、日志级别使用规范

| 级别 | 使用场景 | 示例 |
| --- | --- | --- |
| `DEBUG` | 调试细节，生产环境不输出 | 每帧状态、每个工具调用参数、向量相似度分数 |
| `INFO` | 正常运行的关键节点 | 决策完成、动作执行成功、对局开始/结束、API 请求 |
| `WARNING` | 异常但可恢复/降级 | 工具调用超时降级 mock、费用读数 uncertain、图谱加载慢 |
| `ERROR` | 错误但不崩溃 | 单个动作执行失败、数据文件损坏被跳过、API 500 |
| `CRITICAL` | 系统级崩溃 | 模型加载失败、GPU OOM、数据库连接失败 |

## 二、关键路径必须打日志的点

### Agent 决策循环
- 每步决策完成：`INFO` 记录 step_index / action / confidence / 总耗时
- 知识检索：`DEBUG` 记录每个工具的耗时和命中数
- 慢思考：`DEBUG` 记录 reasoning 摘要和 token 数
- 快反应：`DEBUG` 记录触发原因和操作序列

### 感知层
- 截屏失败：`ERROR`
- OCR 读数 uncertain：`WARNING`
- 敌人确认（estimated→cv）：`INFO`
- VLM 分析完成：`DEBUG`

### 动作执行
- 动作执行成功：`DEBUG`
- 动作执行失败：`WARNING`（不中断序列）
- ADB 连接失败：`ERROR`

### 知识库
- 爬虫：每个页面抓取结果（`INFO` 成功 / `WARNING` 失败重试 / `ERROR` 放弃）
- RAG 构建：每 100 个文档进度（`INFO`）
- 图谱构建：节点/边统计（`INFO`），坏文件跳过（`WARNING`）
- MCP 工具调用：`DEBUG` 记录参数和返回 found 状态

### API 层
- 所有请求：中间件自动记录（方法/路径/状态码/耗时）
- 健康检查：`DEBUG`
- 5xx 错误：`WARNING`

## 三、日志格式规范

```python
import logging
logger = logging.getLogger(__name__)

# 推荐格式：模块 事件 关键参数
logger.info("decision step=%d action=%s confidence=%.2f latency=%.1fms",
            step, action, confidence, elapsed_ms)

# 不要用 f-string（避免不必要的字符串拼接开销）
logger.info("decision step=%s", step)  # ✅
logger.info(f"decision step={step}")    # ❌（虽然 Python 3.8+ 性能差异小，但保持一致）
```

## 四、print vs logging

| 场景 | 用 print | 用 logging |
| --- | --- | --- |
| CLI 脚本进度输出（用户直接运行） | ✅ | - |
| 库/模块内部运行日志 | - | ✅ |
| 调试临时输出 | ✅（用完即删） | - |
| API 请求日志 | - | ✅（中间件） |
| 错误信息 | - | ✅（logger.error） |

**当前状态**：核心模块（agent/knowledge/perception/action/env/api）的 print 主要在 CLI 入口（`if __name__ == "__main__"`）和爬虫脚本（用户直接运行时需要进度），属于合理使用。API 层已加请求日志中间件。

## 五、API 请求日志中间件

`api/server.py` 的 `create_app()` 内置请求日志中间件：

```
[arknights.api] GET /api/operator/能天使 -> 200 (2.1ms)
[arknights.api] GET /api/health -> 200 (0.3ms)   # DEBUG 级别
[arknights.api] GET /api/nonexistent -> 500 (1.2ms)  # WARNING 级别
```

- 健康检查/文档/静态资源：`DEBUG`
- 正常请求：`INFO`
- 5xx 错误：`WARNING`

## 六、后续建议

1. **结构化日志**：V100 上线后考虑用 `python-json-logger` 输出 JSON 格式日志，便于 ELK/Loki 收集
2. **日志轮转**：对局日志文件较大时用 `RotatingFileHandler`
3. **trace_id**：跨模块调用链加 trace_id，便于追踪一次决策的完整日志
4. **CI 日志检查**：加一个 lint 规则，禁止核心模块新增 `print(`（CLI 入口除外）
