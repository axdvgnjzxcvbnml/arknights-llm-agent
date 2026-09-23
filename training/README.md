# training —— V100 训练

- `sft_data_prep.py`：把爬取的攻略、录制的对局转换成 SFT 训练数据
- `sft_train.py`：SFT 微调脚本（LoRA，TODO-V100）
- `dpo_train.py`：DPO 偏好训练（TODO-V100）

训练数据落在 `data/sft_data/`（gitignore）。

> 详细训练流程、数据格式、超参见第七批补充的 `training/README.md` 与 `configs/training.yaml`。
