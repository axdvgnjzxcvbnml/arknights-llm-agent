"""training 包：V100 训练。

- sft_data_prep：CPU 真实实现，MAA 作业 + PRTS -> question/answer JSONL；
- sft_train / dpo_train：仅骨架，真实训练 # TODO-V100。

为支持 `python -m training.sft_data_prep`，本 __init__ 不预先导入子模块
（子模块请显式 `from training.sft_data_prep import ...`）。
import training 不拉起 torch/transformers/peft。
"""

from .config import load_training_config

__all__ = ["load_training_config"]
