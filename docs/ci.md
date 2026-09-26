# CI 配置说明

> 配置文件：`.github/workflows/ci.yml`
> 触发：push 到 main / PR 到 main

## Job 总览

| Job | 名称 | 依赖 | 超时 | 阻塞 | 说明 |
| --- | --- | --- | --- | --- | --- |
| syntax-check | 语法检查（Python 3.8 兼容） | 无 | 10min | ✅ | ast.parse 强制 feature_version=(3,8) |
| smoke-test | 冒烟测试（mock 全链路） | syntax-check | 15min | ✅ | bash scripts/run_smoke.sh |
| pytest-core | 单元测试 - 核心模块 | syntax-check | 15min | ✅ | agent/action/env/strategy/e2e |
| pytest-knowledge | 单元测试 - 知识库+感知 | syntax-check | 15min | ✅ | knowledge/perception/crawler |
| pytest-other | 单元测试 - API+训练+视频+脚本 | syntax-check | 15min | ✅ | api/training/chart_reader/scripts/project_status |
| env-check | 环境检查 | syntax-check | 10min | ✅ | bash scripts/check_env.sh |
| frontend-build | 前端构建（frontend/） | syntax-check | 15min | ✅ | npm install + npm run build |
| frontend-test | 前端测试（vitest） | syntax-check | 15min | ✅ | npm test（vitest run） |
| coverage | 覆盖率报告（不阻塞） | syntax-check | 20min | ❌ | pytest --cov，上传 artifact |

## 设计原则

### 1. 最小依赖原则
每个 Python job 只装运行该组测试所需的最小依赖（numpy/pydantic/pyyaml/rich/networkx/fastapi/httpx/pytest），不装 torch/transformers/chromadb/paddleocr/ultralytics 等重包。真实路径在代码内懒加载，mock 用例不需要重包。

### 2. 数据依赖自动 skip
所有需要真实 PRTS 数据/图谱/向量库/模拟器/GPU 的测试用例都有 `pytest.skipif` 守卫，CI 环境（无 data/）自动跳过。集成测试 `tests/test_api_integration.py` 也在此列。

### 3. pytest 分组
全量测试按模块分为 3 组并行运行，缩短 CI 总时长：
- **pytest-core**：agent/action/env/strategy/e2e（决策与环境核心）
- **pytest-knowledge**：knowledge/perception/crawler（知识库与视觉）
- **pytest-other**：api/training/chart_reader/scripts/project_status（API/训练/视频/工具）

### 4. 前端 CI
- Node 20 + npm install（package-lock.json 不在仓库，用 install 而非 ci）
- 构建和测试分开两个 job，可并行
- 前端测试用 vitest（jsdom 环境），覆盖 EvidenceBadge/usePolling/deepCamelize/client

### 5. 覆盖率不阻塞
coverage job 设置 `continue-on-error: true`，失败不影响合并。覆盖率报告作为 artifact 上传，供后续分析。

## 本地复现

```bash
# 语法检查
python -c "import ast,pathlib,sys; [ast.parse(p.read_text(),feature_version=(3,8)) for p in pathlib.Path('.').rglob('*.py') if '.git' not in p.parts]"

# 冒烟
bash scripts/run_smoke.sh

# 单元测试（全量，本地有数据时会跑集成测试）
python -m pytest tests -q

# 前端
cd frontend && npm install && npm run build && npm test
```

## 已知限制

1. **集成测试不在 CI 跑**：`tests/test_api_integration.py` 需要真实 PRTS 数据（5516 文件）和图谱（83MB），CI 环境没有，自动 skip。本地有数据时可跑。
2. **前端 package-lock.json 不在远端**：7 个硬阻塞文件之一（2 个 package-lock + 5 张 PNG），CI 用 npm install 而非 npm ci，安装时间略长但功能等价。
3. **覆盖率不精确**：CI 只装最小依赖，部分模块（torch/transformers 路径）无法导入，覆盖率偏低。本地全量安装后覆盖率更准。
