# mock —— Mock 数据（可提交）

冒烟测试用的假数据：假截图路径、假游戏状态、假检索结果等，随 mock 模块（第三~六批）一起落地。

- `maa_job_3-8.json`（第七批）：自造的 MAA 作业(maa-copilot) schema 子集小样例，
  仅用于 `training/sft_data_prep.py` 的 CPU 联调；非 MAA 官方/真实抄作业数据，
  所用干员名为 PRTS 语料中真实存在的实体。

原则：**不包含**任何 PRTS 版权素材与真实游戏截图、不分发 MAA 官方作业/资源，
全部为程序生成或自造的占位数据。
