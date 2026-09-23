# scripts —— 工具脚本

| 脚本 | 用途 | 状态 |
|---|---|---|
| `run_smoke.sh` | 冒烟测试（mock 全链路，CPU 可跑，无 GPU/模拟器/数据），三段 | ✅ 视觉 + Agent + 环境 |
| `smoke_perception.py` | 截屏→OCR/地图→状态(波次+敌情确认)→VLM→状态报告→`[7/7]` MockActionExecutor 动作编排 | ✅ |
| `smoke_agent.py` | Agent 闭环：感知→知识→慢思考→桥接→快反应→执行→反思，落可解释决策日志 | ✅ 第五批 |
| `smoke_env.py` | Gym 风格环境跑完整两局：10 步通关 / 3 步失败，落对局报告（含每步奖励） | ✅ 第六批 |
| `check_env.sh` | 环境检查（必需依赖缺失则失败；GPU/adb 仅提示） | ✅ 最小版，第八批扩 GPU 侧 |
| `setup_env.sh` | 安装依赖 | 第八批 |
| `crawl_prts.sh` | 爬取 PRTS Wiki | 第八批 |
| `build_rag.sh` | 构建向量库 | 第八批 |
| `build_graph.sh` | 构建知识图谱 | 第八批 |
| `v100_step1_setup.sh` ~ `v100_step5_eval.sh` | V100 上线五步 | 第八批 |

## run_smoke.sh

```bash
bash scripts/run_smoke.sh
```

第三批覆盖视觉 mock 全链路，末尾打印「游戏状态报告」（费用/手牌/技能/波次(含
estimated·cv 标注)/可部署格/VLM 局势与建议/证据分级），并落一份到
`results/perception_smoke_report.txt`（results 已 gitignore），含完整性断言。

第五批新增第二段 `smoke_agent.py`：跑一个会随部署演进的假战局（先锋→医疗→狙击→等待），
逐步打印慢思考 reasoning、evidence 引用、慢快桥接、快通道拦截、执行结果与自我反思，
完整可解释决策日志落到 `results/agent_decision_log.txt`（gitignore），含 14 项完整性断言。
两段任一断言不满足则非 0 退出。
