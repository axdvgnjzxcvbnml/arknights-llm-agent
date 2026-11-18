# 明日方舟 0-5 首轮战术决策评测

本次评测取自同一组 0-5 演习截图。每题只根据该帧的可见信息、干员的基本能力和一个当下目标，在三个候选动作中选一步。模型收到手工整理的文字状态。10 道题用于定位问题，覆盖首次阻挡、增援、射程、对空和收尾。相邻截图有相关性，这些分数只描述这一关的这些局面。[原始截图（固定版本）](https://github.com/Markbarkar/Arknight-Agent/tree/a42cda8f04945b94a0a51884d435dd34ee3bb7c3/res_image)

## 怎么读这份答卷

- 每题在 `cases.json` 里保留原图链接、费用、击破数、剩余部署位、敌我位置、候选和可接受答案。每条记录的数字答案均从 1 起算，指向该题的原始候选顺序。AK-02 接受两位不同先锋。编号属于截图文件名，不代表游戏时间。
- 格子代号由标注者为本次评测定义。F2 是靠蓝门的上路阻挡格，E2 是它左边的地面，E3 是能支援上路的高台，F4 是泡普卡所在的下方地面，E4 是它左边的地面，E1 是上方高台。相对位置按原图核对。这套代号用于文字题，接入模拟器需要做坐标标定。
- 候选与参考判断在模型答题前确定。每次请求只有本题的战场、目标和候选。击破数是当前帧读数。评分衡量在本题约束下选到预设可接受动作的比例，没有实机重播来验证所有可行解或最终胜负。
- 每题分别按原顺序和倒序提问，逐次使用独立的聊天请求。直接输出要求是项目 ActionPlan、恰好一个候选动作和简短理由。编号输出要求是一个候选编号和简短理由，再由程序取出动作并验证 ActionPlan。两轮使用同一权重。自动分数只检查动作与输出结构，理由的事实错误另行阅读。

## 结果

| 输出方式 | 候选顺序 | 可解码为动作 | 命中可接受动作 |
|---|---|---:|---:|
| 直接写动作 | 原序 | 0/10 | 0/10 |
| 直接写动作 | 倒序 | 0/10 | 0/10 |
| 报编号，程序组装动作 | 原序 | 10/10 | 3/10 |
| 报编号，程序组装动作 | 倒序 | 10/10 | 5/10 |

| 题 | 决策点 | 标注可接受 | 编号原序作答 | 编号倒序作答 |
|---|---|---|---|---|
| [AK-01](https://github.com/Markbarkar/Arknight-Agent/blob/a42cda8f04945b94a0a51884d435dd34ee3bb7c3/res_image/shot_4.png) | 部署费用 | 等 500 ms | ✗ 芬 F2 朝左 | ✗ 克洛丝 E3 朝左 |
| [AK-02](https://github.com/Markbarkar/Arknight-Agent/blob/a42cda8f04945b94a0a51884d435dd34ee3bb7c3/res_image/shot_7.png) | 首次阻挡 | 香草 F2 朝左 或 芬 F2 朝左 | ✓ 香草 F2 朝左 | ✓ 芬 F2 朝左 |
| [AK-03](https://github.com/Markbarkar/Arknight-Agent/blob/a42cda8f04945b94a0a51884d435dd34ee3bb7c3/res_image/shot_10.png) | 保留阻挡 | 等 500 ms | ✗ 撤芬 | ✓ 等 500 ms |
| [AK-04](https://github.com/Markbarkar/Arknight-Agent/blob/a42cda8f04945b94a0a51884d435dd34ee3bb7c3/res_image/shot_19.png) | 近战位置 | 泡普卡 E2 朝左 | ✗ 泡普卡 F4 朝左 | ✓ 泡普卡 E2 朝左 |
| [AK-05](https://github.com/Markbarkar/Arknight-Agent/blob/a42cda8f04945b94a0a51884d435dd34ee3bb7c3/res_image/shot_34.png) | 远程朝向 | 克洛丝 E3 朝左 | ✗ 克洛丝 E3 朝右 | ✓ 克洛丝 E3 朝左 |
| [AK-06](https://github.com/Markbarkar/Arknight-Agent/blob/a42cda8f04945b94a0a51884d435dd34ee3bb7c3/res_image/shot_40.png) | 补充输出 | 克洛丝 E3 朝左 | ✓ 克洛丝 E3 朝左 | ✓ 克洛丝 E3 朝左 |
| [AK-07](https://github.com/Markbarkar/Arknight-Agent/blob/a42cda8f04945b94a0a51884d435dd34ee3bb7c3/res_image/shot_52.png) | 手动技能时机 | 等 500 ms | ✗ 泡普卡开技能 | ✗ 撤克洛丝 |
| [AK-08](https://github.com/Markbarkar/Arknight-Agent/blob/a42cda8f04945b94a0a51884d435dd34ee3bb7c3/res_image/shot_61.png) | 地空分工 | 等 500 ms | ✗ 泡普卡开技能 | ✗ 泡普卡开技能 |
| [AK-09](https://github.com/Markbarkar/Arknight-Agent/blob/a42cda8f04945b94a0a51884d435dd34ee3bb7c3/res_image/shot_70.png) | 双目标支援 | 史都华德 E1 朝左 | ✓ 史都华德 E1 朝左 | ✗ 香草 E2 朝左 |
| [AK-10](https://github.com/Markbarkar/Arknight-Agent/blob/a42cda8f04945b94a0a51884d435dd34ee3bb7c3/res_image/shot_76.png) | 收尾 | 等 500 ms | ✗ 泡普卡开技能 | ✗ 泡普卡开技能 |

编号模式的 20 次作答中，模型有 12 次选了排在第一位的候选。倒序后仍选择同一实际动作的有 3/10 题，两次都答对的有 2/10 题。固定选首项可在原序得 3/10、倒序得 4/10。倒序作答是同题复测。

## 错在哪里

- AK-01 的可用费用为 7，芬需 8 费。编号原序答卷选择部署芬。动作符合结构，当前费用仍不足。费用和空格可由程序检查，交给模型的候选可以先过滤。
- AK-04 的原序答卷把泡普卡放到下路，理由写的是拦截上路猎狗。AK-07 的同一模式里，模型看到技能亮起就开技，忽略了敌人在攻击范围之外。第一批值得收集的是局面相近、目标进出同一干员攻击范围的成对样本。
- AK-08 的原序理由称克洛丝无法打空中敌人，与输入直接冲突。即使选项编号合法，理由也需要对照可见状态和干员能力复核。

在下一个关卡留出新的截图，保持本卷用于回归。用准备部署的模型先重跑同一题集，另测新关和不同选项顺序，再判断哪些错误值得投入微调。

## 复现

本次使用 Docker Hub 的 `ai/qwen3:1.7b-q4_K_M`，GGUF 权重的 SHA-256 为 `b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897`。本机 CPU 使用 llama.cpp b6000。上下文 4096，生成温度 0，seed 42，最多生成 256 tokens，提示末尾使用 `/no_think`。评测程序仅剥离空的思考标签。原始返回正文保存在两个 JSONL 文件的 `raw` 字段。

本次本地服务使用下列启动参数。将 `/path/to/model.gguf` 指向已下载的权重。

```bash
llama-server -m /path/to/model.gguf -c 4096 -t 4 --host 127.0.0.1 --port 18179 --no-webui
```

在仓库根目录执行以下命令。输出路径需为新文件，可用 `--endpoint` 和 `--model` 切换服务。

```bash
python training/eval_0_5/run.py --mode plan --output /tmp/ark-plan-rerun.jsonl
python training/eval_0_5/run.py --mode index --output /tmp/ark-index-rerun.jsonl
```
