# .github/workflows —— GitHub Actions 工作流

- `ci.yml`：push / PR 时运行三个 job：
  1. `syntax-check`：Python 3.8 语法兼容性检查（`ast.parse(feature_version=(3, 8))`）
  2. `smoke-test`：冒烟测试，mock 全链路，不依赖 GPU / 模拟器 / PRTS 数据
  3. `env-check`：环境检查

说明：`smoke-test` 与 `env-check` 依赖 `scripts/run_smoke.sh`、`scripts/check_env.sh`（第八批实现），本工作流先就位，全部变绿为第九批验收点。
