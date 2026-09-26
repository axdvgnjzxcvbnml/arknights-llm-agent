# 错误消息质量审计

> 审计时间：2026-09-27
> 范围：全仓库 raise 语句和错误返回值

## 评估标准

好的错误消息应包含三要素：
1. **哪里错了**（上下文：哪个模块/哪个操作/哪个输入）
2. **为什么错了**（原因：文件不存在/格式错误/超时/参数非法）
3. **怎么修**（建议：检查路径/安装依赖/查看文档/重试）

## 优秀示例

| 位置 | 错误消息 | 评分 |
| --- | --- | --- |
| `env/episode_store.py:46` | "非法 episode id（仅允许字母数字 _ -，1-128 位）：%r" | ✅ 三要素齐全 |
| `knowledge/rag/embedding.py` | "embedding 模型加载失败：%s。检查网络或设置 backend=mock" | ✅ 含修复建议 |
| `action/adb_controller.py` | "ADB 连接失败：%s。检查 MuMu 是否启动、adb connect 127.0.0.1:7555" | ✅ 含修复建议 |
| `video_extract/chart_reader.py:99` | "TODO-V100: 未配置 VLM 模型...在 V100 上填 Qwen/Qwen3-VL-8B..." | ✅ 含具体操作指引 |

## 需改进的错误消息

| 位置 | 当前消息 | 问题 | 建议 |
| --- | --- | --- | --- |
| 部分 `raise ValueError` | "invalid input" | 缺上下文和原因 | 改为 "invalid input for %s: got %r, expected %s" |
| 部分 `except Exception as e: raise` | 原始异常透传 | 缺上下文 | 改为 `raise XxxError("failed to %s: %s" % (op, e)) from e` |
| API 404 | "not found" | 缺哪个资源 | 改为 "episode not found: %s" % episode_id |

## 错误类型分布

| 异常类型 | 数量（约） | 主要用途 |
| --- | --- | --- |
| `ValueError` | 20+ | 参数校验、配置错误 |
| `NotImplementedError` | 15+ | TODO-V100 占位 |
| `FileNotFoundError` | 5+ | 数据文件缺失 |
| `ChartReadError` | 自定义 | 图表读取失败 |
| `InvalidEpisodeId` | 自定义 | 对局 ID 非法 |
| `ADBControllerError` | 自定义 | ADB 操作失败 |
| `GraphUnavailable` | 自定义 | 图谱不可用 |

## 改进建议

1. **统一异常基类**：核心模块定义 `ArknightsError` 基类，所有自定义异常继承
2. **异常链**：`raise NewError(...) from e` 保留原始异常栈
3. **错误码**：API 层错误返回结构化 `{code, message, detail}`，便于前端处理
4. **CI 检查**：加 lint 规则禁止 `raise Exception("error")` 这类无上下文消息
