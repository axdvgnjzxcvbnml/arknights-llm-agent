# AGENTS.md

> 仓库协作规范与边界定义
> 最后更新：2026-09-30

## 一、唯一真相源

**GitHub 主仓 `axdvgnjzxcvbnml/arknights-llm-agent`（main 分支）是唯一真相源。**

- 所有代码、文档、配置以 main 分支为准
- 本地工作区是临时的，任何改动必须推送到 main 才算完成
- 云沙箱环境不可靠（曾发生过串目录、工作区损坏），不要依赖本地持久化

## 二、工作流

### 2.1 分支 + PR 模式

所有改动走「分支 + PR」，禁止直接 push main：

```
1. 从 main 创建功能分支
2. 在分支上开发、测试
3. 推送分支到 GitHub
4. 创建 PR，描述改动内容和验证方式
5. 审查通过后 merge 到 main
```

### 2.2 分支命名

| 分支名 | 用途 | 操作者 |
|--------|------|--------|
| `agent/doubao/*` | 豆包助手的改动 | doubao |
| `agent/qwen/*` | Qwen 助手的改动 | qwen |
| `agent/workbuddy/*` | WorkBuddy 助手的改动 | workbuddy |
| `agent/kimi/*` | Kimi 助手的改动 | kimi |
| `fix/*` | 紧急修复 | 任意 |
| `feat/*` | 新功能 | 任意 |

示例：`agent/doubao/frontend-merge`、`agent/qwen/replay-page`、`fix/api-400-error`

### 2.3 Commit 规范

```
<type>(<scope>): <subject>

<body>

<footer>
```

- type: `feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `perf`
- scope: 模块名（`frontend` / `api` / `knowledge` / `training` / `env` / `agent` / `perception` / `action` / `video_extract` / `ci`）
- subject: 简明描述（不超过 50 字）
- body: 详细说明（可选）
- footer: 关联 Issue/PR（可选）

示例：
```
feat(frontend): 三路合并 web/(对局回放) + web-kb/(知识库) 到统一 frontend/

- Phase 1: 移植 web-kb 三页（RAG/图谱/干员详情）
- Phase 2: 移植 web/ 对局回放（20组件+2hooks+api）
- Phase 3: 删除独立工程目录，更新 README
- 构建通过：974KB bundle，8路由就绪
```

## 三、各 Agent 边界

### 3.1 Doubao（本助手）

**负责：**
- 后端 API（`api/`）
- 数据管线（`knowledge/crawler/`、`knowledge/rag/`、`knowledge/graph/`）
- MCP 工具（`knowledge/mcp_tools/`）
- 训练脚本（`training/`）
- Agent 核心（`agent/`）
- 环境封装（`env/`）
- 感知模块（`perception/`）
- 动作执行（`action/`）
- 视频提取（`video_extract/`）
- CI/CD（`.github/workflows/`）
- 文档（`docs/`）
- 配置（`configs/`）
- 脚本（`scripts/`）

**不碰：**
- `frontend/`（前端代码，由 Qwen/Kimi 负责）
- 除非是前端构建配置（`vite.config.ts`、`package.json` 依赖）或类型定义

### 3.2 Qwen

**负责：**
- `frontend/` 中的对局回放页面（`pages/Replay.tsx`、`components/replay/`）
- 对局回放相关的类型定义和 API 封装

### 3.3 Kimi

**负责：**
- `frontend/` 中的知识库页面（`pages/kb/`）
- 知识库相关的组件和类型定义

### 3.4 WorkBuddy

**负责：**
- 代码审计、质量检查
- 测试覆盖率分析
- 性能基准测试
- 不直接修改业务代码，只出报告和建议

## 四、API 契约

**API 契约冻结后，任何改动必须走 PR + 版本号升级。**

- 契约文档：`docs/api-contract.md`
- OpenAPI schema：`docs/openapi.yaml`
- 契约测试：`tests/test_api_contract.py`（CI 自动运行）
- 版本策略：`/api/v1/` 前缀，breaking change 必须升版本号

## 五、数据安全

### 5.1 禁止入库的内容

以下内容**绝对不能**提交到 git：

- `data/prts_raw/`（爬虫原始数据）
- `data/vector_store/`（向量库）
- `data/graph/`（图谱数据）
- `data/sft_data/`（SFT 训练数据）
- `data/video_raw/`（视频原始文件）
- `data/video_frames/`（视频抽帧）
- `weights/`（模型权重）
- `results/`（运行结果、benchmark 数据）
- `.env`、`*.pem`、`*.key`（密钥和证书）
- `*.pth`、`*.pt`、`*.onnx`（模型文件）
- `.coverage`（coverage 数据文件）

### 5.2 推送前检查

每次推送前必须运行：

```bash
# 检查是否有敏感文件被跟踪
git ls-files | grep -E "(prts_raw|vector_store|sft_data|weights|results|\.env|\.pth|\.pt|\.onnx|\.coverage)"

# 密钥扫描（如果有工具）
python -m scripts/check_secrets.py
```

## 六、V100 相关

- V100 服务器是用户的单卡服务器（sm_70，16GB 显存）
- 助手**不访问** V100 服务器和数据集
- 所有 GPU 相关代码标注 `# TODO-V100`，CPU 侧只做骨架和 mock
- V100 上线后的操作清单：`docs/v100_handoff.md`、`docs/v100_checklist.md`

## 七、与毕设仓库的隔离

- 本仓库：`arknights-llm-agent`（明日方舟 LLM Agent）
- 毕设仓库：`pointcloud-registration-detection`（深度相机点云拼接与 3D 目标检测）
- **两个仓库完全隔离**，代码、数据、配置互不重叠
- 新会话开始时，第一句话必须锁定「项目目录 + GitHub 仓库名」

## 八、常见问题

### Q: 可以直接 push main 吗？
A: 不可以。所有改动走分支 + PR。紧急修复可以用 `fix/*` 分支，但仍需 PR。

### Q: 前端代码谁负责？
A: Qwen 负责对局回放，Kimi 负责知识库。Doubao 不碰 `frontend/` 的业务代码，只维护构建配置和类型定义。

### Q: 数据文件可以提交吗？
A: 不可以。`data/`、`weights/`、`results/` 下的所有内容都在 `.gitignore` 里，绝对不能提交。

### Q: 云沙箱环境坏了怎么办？
A: 从 GitHub main 分支重新 clone。本地工作区是临时的，main 分支是唯一真相源。

### Q: 多个 Agent 同时改一个文件怎么办？
A: 各自在自己的分支上开发，merge 时解决冲突。如果冲突复杂，先沟通再 merge。
