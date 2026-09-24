#!/usr/bin/env bash
# V100 视觉训练（第二步）。无 GPU 安全中止（退出码 3）。
set -euo pipefail
cd "$(dirname "$0")/.."

python - <<'PY'
import torch
if not torch.cuda.is_available():
    raise SystemExit(3)
PY
status=$?
if [ $status -eq 3 ]; then
  echo "[GPU 门禁] 未检测到 CUDA，安全中止（不做假训练）。" >&2
  exit 3
fi

echo "== Step2: 视觉训练（YOLOv8n） =="
echo "[清单 # TODO-V100]"
echo "1. 录制真实出怪时间轴 -> configs/perception.yaml 的 spawn.timeline (annotated)"
echo "2. YOLOv8n 数据准备：截图裁剪/标注 -> yolov8n_arknights.pt"
echo "3. 填充 perception/detector_yolo.py 的 detect() 与 confirm_spawn()"
echo "4. 校准 ROI: cost_box/技能按钮/卡牌槽/格子网格/enemy_confirm_region"
echo "5. 冒烟: 真实截屏 -> state_parser 输出 GameState JSON"
echo "参考: docs/v100_checklist.md Step2"

echo "== Step2 完成（清单执行） =="
echo "下一步: bash scripts/v100_step3_sft.sh"
