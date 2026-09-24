#!/usr/bin/env bash
# V100 Step4：部署 Agent —— 知识库/MCP 就绪检查 + mock 闭环回归 + 真机/模型接入指引。
# 真实慢思考/快反应/VLM 模型加载需要 V100；无 GPU 时由门禁拦截（退出码 3）。
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PYTHON:-python3}"

echo "===== V100 Step4：部署前检查 ====="

# ---- 知识库产物（可选：没建库也能用 mock，但真机决策需要）----
if [[ -f data/graph/arknights_graph.graphml ]]; then
  echo "[OK] 知识图谱已构建：data/graph/arknights_graph.graphml"
else
  echo "[WARN] 知识图谱缺失：bash scripts/build_graph.sh"
fi
if [[ -f data/vector_store/chroma.sqlite3 ]] || [[ -d data/vector_store ]]; then
  echo "[OK] 向量库目录存在：data/vector_store/"
else
  echo "[WARN] 向量库缺失：bash scripts/build_rag.sh"
fi

# ---- 先用 CPU mock 闭环回归，保证部署基线不被破坏 ----
echo
echo "[deploy] 先跑 mock 全链路回归（不依赖 GPU/模拟器）..."
bash scripts/run_smoke.sh

# ---- GPU 门禁 ----
if ! "$PY" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
  echo
  echo "[GATE] mock 回归通过；真实模型部署需要 V100（当前无 CUDA），在此中止（退出码 3）。"
  exit 3
fi

echo
echo "===== V100 真机部署（按序执行）====="
cat <<'MSG'
  # TODO-V100: slow_thinker/fast_reactor/latent_bridge/vlm_analyzer 的真实模型加载仍为骨架。
  1) 连接模拟器：  adb connect 127.0.0.1:7555   # MuMu 默认端口；校准 configs/perception.yaml
  2) 启动 MCP：   python -m knowledge.mcp_tools.server    # stdio，供 Agent 调用知识库工具
  3) 加载模型：   Qwen3-8B-Thinking(慢) / 小模型(快) / Qwen3-VL-8B 或 UI-TARS-7B(慢通道)
                  在 agent/*.py 的 # TODO-V100 处接入 LoRA 权重 weights/sft_qwen3_lora
  4) 注入真实组件到 env.ArknightsEnv（perception=ADB+CV，executor=真实 ADB），先打简单关。
MSG
echo
echo "本步骤完成（mock 回归已过，真机接入按上述清单）。下一步：bash scripts/v100_step5_eval.sh"
