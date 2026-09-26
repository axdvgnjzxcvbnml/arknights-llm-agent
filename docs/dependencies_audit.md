# 项目依赖审计

> 审计时间：2026-09-27
> 范围：requirements.txt + pyproject.toml

## 一、依赖分类

### 核心依赖（CPU 冒烟必需，12 个）
| 包 | 用途 | 版本约束 |
| --- | --- | --- |
| pydantic | 数据模型/结构化输出 | 无（>=2.0） |
| pyyaml | 配置文件解析 | 无 |
| requests | 爬虫/API 调用 | 无 |
| beautifulsoup4 | HTML 解析 | 无 |
| lxml | HTML/XML 解析器 | 无 |
| networkx | 知识图谱 | 无 |
| fastapi | API 服务端 | 无 |
| uvicorn | ASGI 服务器 | 无 |
| rich | 终端美化输出 | 无 |
| typer | CLI 框架 | 无 |
| pytest | 单元测试 | dev |
| numpy | 数值计算（传递依赖） | 无 |

### 知识库依赖（6 个）
| 包 | 用途 | 备注 |
| --- | --- | --- |
| chromadb | 向量数据库 | Python>=3.9；V100 用 3.8 需固定 0.4.24 |
| sentence-transformers | 中文 embedding | V100 用 3.8 需固定 2.2.2 |
| rank_bm25 | BM25 关键词检索 | 轻量，纯 Python |
| jieba | 中文分词 | BM25 索引构建 |
| matplotlib | 图谱可视化 | 仅 visualize_graph.py 使用 |

### V100 专属依赖（6 个）
| 包 | 用途 | 备注 |
| --- | --- | --- |
| torch | 深度学习框架 | V100 用 1.13.1+CUDA11.7 |
| transformers | 模型加载/推理 | V100 用 4.36.2 |
| ultralytics | YOLOv8 检测 | 需训练数据 |
| paddleocr | OCR 费用识别 | CPU 可跑，V100 加速 |
| opencv-python | 图像处理 | 传递依赖 |
| mcp | Model Context Protocol | 工具调用协议 |

### 环境通信依赖（4 个，可选）
| 包 | 用途 | 备注 |
| --- | --- | --- |
| paho-mqtt | MQTT 消息 | 预留，当前未使用 |
| grpcio | gRPC 通信 | 预留，当前未使用 |
| redis | Redis 缓存 | 预留，当前未使用 |
| websockets | WebSocket | /ws/live 使用 |

## 二、发现的问题

### 1. 未使用的依赖（3 个，预留但未接入）
| 包 | 状态 | 建议 |
| --- | --- | --- |
| paho-mqtt | 预留，代码中无 import | 移到 optional-dependencies，或标注 TODO |
| grpcio | 预留，代码中无 import | 同上 |
| redis | 预留，代码中无 import | 同上 |

### 2. 版本冲突风险
- **chromadb / sentence-transformers / transformers**：沙箱 Python 3.12 用最新版，V100 Python 3.8 需固定旧版。requirements.txt 已注明，但未用 `python_version` 条件区分。
- **torch**：V100 需 CUDA 11.7 版本，CPU 沙箱用 CPU 版。requirements.txt 未区分。

### 3. 重复依赖
- requirements.txt 和 pyproject.toml 的 dependencies 有重复（torch/transformers/requests 等）。建议以 pyproject.toml 为唯一来源，requirements.txt 用 `pip install -e .` 生成。

### 4. 安全漏洞
- 未运行 pip-audit（沙箱网络受限）。建议 V100 上线后跑 `pip-audit` 检查。

## 三、改进建议

1. **短期**：将 paho-mqtt/grpcio/redis 移到 `optional-dependencies` 的 `comm` 组，避免默认安装未使用的包
2. **中期**：用 `python_version` 条件区分 V100 (3.8) 和沙箱 (3.12) 的依赖版本
3. **长期**：以 pyproject.toml 为唯一依赖来源，requirements.txt 改为 `pip install -e .[dev]` 的快捷方式
4. **V100 上线后**：跑 `pip-audit` 检查安全漏洞，定期更新依赖

## 四、依赖体积估算

| 分类 | 包数 | 预估安装体积 |
| --- | --- | --- |
| 核心（CPU 冒烟） | 12 | ~200MB |
| + 知识库 | 6 | ~500MB（含 sentence-transformers 模型下载） |
| + V100 专属 | 6 | ~3GB（含 torch CUDA 版） |
| + 环境通信（可选） | 4 | ~50MB |
| **完整安装** | **28** | **~4GB** |
