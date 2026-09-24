#!/usr/bin/env bash
# V100 Step2：视觉模型训练（YOLOv8n 干员/敌人检测；PaddleOCR 费用真机校准）。
# 本步骤需要 V100 + CUDA；在无 GPU 机器上由 GPU 门禁拦截（退出码 3，不做任何训练）。
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY="${PYTHON:-python3}"

# ---- GPU 门禁 ----
if ! "$PY" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
  echo "[GATE] 需要 V100（CUDA 不可用）。本步骤为 GPU 训练，已在无 GPU 环境中止（未做任何训练）。"
  echo "       请在 V100 机运行；环境核对先执行 bash scripts/v100_step1_setup.sh。"
  exit 3
fi

echo "===== V100 Step2 视觉模型训练 ====="
# TODO-V100: 以下训练入口在 perception/detector_yolo.py 中仍为骨架（NotImplementedError）。
#   真机阶段第一步（见 docs/architecture.md）：先录制真实波次时间轴校准 SpawnTracker，
#   再准备 YOLOv8n 数据集并训练，随后把 confirm_spawn() 由 mock 接到真实检测。
echo "[TODO-V100] 视觉训练代码尚未实现，当前为流程骨架，不进行真实训练。"
echo
echo "在 V100 上需要完成（数据不入库，仅本地）："
cat <<'MSG'
  1) 数据：PRTS 敌人图片 + 真机截图标注（YOLO 格式），放本地数据集目录（勿提交素材）。
  2) 训练 YOLOv8n（干员/敌人检测）：ultralytics，fp16；模型落 weights/（gitignore）。
  3) 实现 perception/detector_yolo.py 中标注 # TODO-V100 的真实 detect()，
     并用 confirm_spawn(enemy, frame) 把 SpawnTracker 的波次状态 estimated -> cv。
  4) PaddleOCR：在 configs/perception.yaml 校准 cost_box；两帧一致性逻辑已就绪。
  5) 校准占位坐标：grid / operator_card_bar / skill_buttons / enemy_confirm_region。
MSG
echo
echo "本步骤完成（骨架说明）。下一步：bash scripts/v100_step3_sft.sh"
