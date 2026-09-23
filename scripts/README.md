# scripts —— 工具脚本

| 脚本 | 用途 | 状态 |
|---|---|---|
| `run_smoke.sh` | 冒烟测试（mock 全链路，CPU 可跑，无 GPU/模拟器/数据） | ✅ 第三批：视觉链路 |
| `smoke_perception.py` | run_smoke 调用的视觉链路：截屏→OCR/地图→状态(波次+敌情确认)→VLM→状态报告 | ✅ |
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
`results/perception_smoke_report.txt`（results 已 gitignore）。内置 12 项完整性断言，
任一不满足则非 0 退出。后续批次会在此扩展动作执行与 Agent 决策闭环。
