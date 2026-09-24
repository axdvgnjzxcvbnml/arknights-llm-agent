# 常见问题与排障（troubleshooting）

本文件记录开发/运行中实际遇到的问题与定位过程，供后续复现与规避。

## 知识库

### 2026-09：RAG 检索 query「3-8 有哪些敌人」首次未命中（已解决）

- **现象**：向量库从 830+ chunk 扩到 863 chunk（补爬 4-7/10-14/10-17 等关卡）后，
  该 query 的目标 chunk（stage/enemies，3-8 敌方情报）从 Top1（相似度 0.78）跌到 161 名
  （0.42），Top5 被描述文本中大量出现"敌人"字样的敌人页占据。
- **原因**：
  1. chunk 标题是陈述句"关卡3-8 出场敌人共 8 种。"，bge-small-zh 对 query 中的
     疑问句式（"有哪些敌人"）匹配偏弱；
  2. 敌情表超过 500 字被切成多块，续块以具体敌人名开头、缺少 query 锚点；
  3. 语料变大后干扰增多，标题语义密度不足的问题被放大。
- **修复**：`knowledge/rag/build_rag.py` 中关卡敌情 chunk 标题改为问句化模板
  「{code}有哪些敌人？关卡{code} 本关敌人配置与出场数量如下，共出场 N 种敌人。」
  （单句嵌入对比：0.65 → 0.79）。修复后该 query 回到 Top1（0.59），5 条测试 query 全命中。
- **经验**：bge 类模型对"标题与 query 同句式"敏感；列表型 chunk 的标题应直接写出
  用户会问的问题，而不是中性陈述句。

### 2026-09：ChromaDB upsert 报 DuplicateIDError（已解决）

- **现象**：扩量后构建报 `Expected IDs to be unique`，重复键来自敌人"变形者集群"。
- **原因**：PRTS 存在消歧义页面"变形者集群"与"变形者集群(DC3)"，解析出的显示名相同，
  chunk/节点 id 按显示名生成导致冲突。
- **修复**：RAG 与图谱的实体身份统一改用**页面标题（文件名）**，显示名仅作属性；
  图谱中关卡敌情表按显示名引用敌人时，经 display→page 映射优先落到无后缀的基础形态。

### 2026-09：知识图谱阈值校准的样本偏置（设计说明）

- 字典序前 52 个敌人页偏活动/肉鸽高数值单位（防御 1000+ 常见），而主线关卡敌情表
  常规敌人防 ≤800、抗 ≤50。阈值若按敌人页分布取值（防1000/抗70），主线关卡
  RECOMMENDS 边为 0；最终阈值锚定主线敌情（防800/抗50/速2.0，见
  `configs/knowledge.yaml` 注释），代价是敌人页一侧职业级克制边较密，
  已用 match_basis（class=1.0 / skill_keyword=0.6）加权 + 按支持度/星级排序缓解。
  语料扩大后需重新校准阈值。

### 2026-09：沙箱 CPU 构建向量库较慢

- 2 核 CPU 上 bge-small-zh 编码约 860 chunk 需 7-8 分钟；模型约 90MB，沙箱可下载。
  全量 13511 chunk（2026-09-24）在同一 2 核环境约 20-22 分钟（与其它任务并发时更久）。
- 离线环境 `rag.embedding.backend: mock` 自动回退确定性伪随机向量（仅用于接口联调，
  检索无意义）；正式检索必须使用真实 bge（V100 上把 device 改 cuda）。

### 2026-09：批量干员 JSON 的 trait（特性）全部为空（已解决）

- **现象**：RAG 重建前审计发现 53 个干员 JSON 的 `trait` 字段全部是 `{}`，
  导致切分时没有 trait chunk，"沉默/停顿/法术伤害"等分支机制文本无法被检索。
- **原因**：PRTS 特性表的数据行是**值对值**（如 `['速射手','优先攻击空中单位']`），
  解析器只接受键值对（`row[0] in ('分支','描述')`），把数据行当成了表头；
  条件式特性表（猎手/链术师等）表头是 `['分支','条件']`，后跟各精英阶段描述行，
  是第二种未覆盖的布局。
- **修复**：`parse_operators._parse_trait` 改为先定位 `['分支','描述']`/`['分支','条件']`
  表头行、再取下一行值；条件式布局收集 `[精英阶段N, 描述]` 拼成可检索文本；
  另解析 `['分支信息']` 标签行。修复后 53/53 干员特性完整（commit 22b70ca）。
- **经验**：批量爬取后不能只验 HTTP 200/JSON 非空，必须按字段做完整性审计；
  解析器修改后要用缓存 HTML 零请求重解析全量 JSON 并重建向量库。

### 2026-09-24：全量语料（460/1807/487）重建后两处检索排序瑕疵（记录，非不命中）

全量库 13511 chunk（真实 bge/512 维），5 条标准 query 仍 **5/5 HIT@5**，但全量后出现两处 Top1 排序问题：

1. **异格干员抢占本体名**：「能天使的技能是什么」Top1–4 一度是异格「新约能天使」，本体技能块排到第 5。
   - 原因：纯向量按字面/语义相似度，chunk 文本「干员新约能天使的技能…」与 query 高度重合，
     embedding 不做实体消歧；样本库时没有异格实体所以未暴露。
   - **已修复（2026-09-24）**：`Retriever` 增加保守的“显式指名”重排——超取候选池（max(K,4K)≤20），
     当 query 原文明确出现某候选实体名（source；关卡取编号前缀）时优先，组内仍按向量分稳定排序。
     ASCII 编号做左右边界校验（避免「1-1」误命中「11-1」），中文做子串匹配；不改向量、evidence 仍 retrieved。
     修复后「能天使的技能」Top1 即本体技能块，3-8/碎骨/先锋等原有 Top1 不受影响（附边界单测）。
   - 后续可选增强：同名仍需多份时做“每 source 去重保 1–2 条”，或在 Agent 侧先用图谱页面标题做实体链接。
2. **「沉默效果是什么」Top1 是诗化文案而非机制解释**：Top1 命中攻略块里的文学句
    「沉默是它对时光的回应」，但 Top2–4 正是含「特性：沉默 · 沉睡　术语:沉默」的敌人/干员机制块，语料里有正确解释。
   - 原因：embedding 难区分「沉默」一词的**机制术语**用法与**普通字面**用法；query 本身也偏模糊。
   - 影响：HIT@5 且紧邻结果相关，仅 Top1 噪声；不算检索失败。
   - 建议：术语类 query 增加关键词/结构加权（命中「术语:」或 section 标记优先）或 BM25+向量混合检索。

对照（全量比样本的增益）：「3-8 有哪些敌人」Top1 精确（共 8 种，与图谱一致）；「碎骨的属性」
Top1–3 直接覆盖碎骨 level0/1/2 三种形态；「先锋干员的费用」Top1 即含「初始部署费用」的先锋 meta 块。
报告：`data/vector_store/retrieval_report_full.json`（gitignore）。

---

## SFT 数据与训练（CPU 预演 / V100）

### 2026-09-24：260/487 关卡的 normal.name 被信息卡 UI 文案污染（已在数据侧绕过，解析器待修）

- **现象**：10 章后带「磨难/险地」难度选择器的关卡，`parse_stages.py` 把整段 UI 文本
  （标准/磨难/险地、理智消耗、掉落、代理指挥说明，约 474 字）塞进了 `normal.name`，
  被 SFT 问题构造引用后会污染 `[关卡]` 行并浪费 token。
- **现状**：这些关卡的**顶层 `name`（如「12-13 逆光阴影」）始终干净**（全 487 个最长 17 字）。
  `sft_data_prep._state_question` 已改为**优先顶层 name**，问题文本不再含 UI 文案。
- **遗留**：根因在爬虫 `knowledge/crawler/parse_stages.py` 的信息卡名称定位，下次需要重爬时
  应修解析器（难度选择器布局下名称单元格的判定），再重爬重建 PRTS 语料与 RAG。

### 2026-09-24：SFT 数据中的职业泛称/空槽占位动作（已剔除）

- 部分 MAA 作业不写具体干员，用「输出/奶盾/单奶/速狙/投锋/快活/工具人」等职业或分支黑话
  占灵活位，另有 MAA 空槽哨兵 `Unknown_EndsEmpty`；这类「deploy 输出」不是可执行策略。
- `sft_data_prep.is_generic_operator` 分两级剔除共 **1646 条**：
  ①38 个职业/黑话精确词 + 空槽哨兵（高精度白名单，宁漏勿错）；
  ②零误伤**结构规则**——练度括号/关键词（`【…】/练度/精一精二/满级/及以上`）、
  “职业-分支”（特种-伏击客）、“职业+编号”（医疗2/铁卫1）、“短词：练度要求”（地刺：精一满级…）。
  真实干员/召唤物/装置名（弦惊/障碍物/地刺/幻影/麒麟X夜刀/御龙：雷狼龙）均有用例保证不误删。
- 疑似具体物昵称（祖宗/书刀等）与无练度标记的纯黑话长尾（铁卫/法师/双击快活等）保留，
  规模与处理建议见 `docs/sft_data_quality.md` §4；训练后若模型学到怪 token 再做 token 白名单净化。
- 同类修复：障碍物/装置无朝向不再生成「facing ?」；按格撤退不再生成「retreat None」；
  召唤物「部署→撤回→再部署」的完全相同 (状态→动作) 对做精确去重（**453** 条）。

### 2026-09-24：CPU 沙箱如何预演 SFT 训练管线（--dry-run）

- **约束**：沙箱 2 核 / 4GB 内存 / 无 GPU；Qwen3-0.6B 权重（fp32 约 2.4GB）叠加 AdamW 状态
  在 4GB 内也不现实，8B 更不可能。真机 fp16 Qwen3-8B（约 8.2B 参数，仅权重 ≈16.4GiB）
  在 V100 16G 上连权重都放不下，必须 QLoRA。
- **做法**（`training/sft_train.py --dry-run`）：
  - 只下载 Qwen3 tokenizer（`Qwen/Qwen3-0.6B`，几 MB，与 8B 同词表），**不下载模型权重**；
  - 用 `Qwen3Config` 构造极小随机模型（2 层/hidden128，约 39M 参数）跑真实
    LoRA→forward→loss→backward→AdamW→保存 adapter→回读前向全链路；
  - 验证的是**数据/掩码/训练/存盘代码路径**（与真机同一份 `Qwen3ForCausalLM`+peft 调用），
    loss 数值无意义（随机小模型），看到有限且略有下降即可。
- **import 必须保持惰性**：torch/transformers/peft 只在函数内 import，
  保证 `import training.sft_train` 在无 GPU 依赖的 CI 里不报错（有专门的 import-light 测试）。
- 沙箱最初缺 peft/accelerate/bitsandbytes：dry-run 只需 `pip install peft`；
  8bit 相关（bitsandbytes）只在真机 `--load-in-8bit` 时导入，CPU 不需要。
- 集成测试默认 skip（要联网下 tokenizer），需显式开启：
  `ARK_RUN_TRAIN_DRYRUN=1 pytest tests/test_training.py`；
  label 掩码/左截断契约另有不依赖 torch 的纯 Python 单测恒跑。
- 真机路径在无 CUDA 时显式 `NotImplementedError(TODO-V100)`，不会在 CPU 静默跑大模型。

### V100 16G 跑 fp16 8B 显存不足 → QLoRA（8bit）

见 `docs/v100_checklist.md`「Step 4 展开：SFT 精确执行手册」。要点：fp16 Qwen3-8B 仅权重
（约 8.2B 参数）≈16.4GiB，16G 卡放不下，必须用 `--load-in-8bit`（8bit 冻结底座 ≈8.0–8.5GiB）
+ gradient checkpointing + micro batch 1，或退回 Qwen3-4B fp16；V100 无 bf16，一律 fp16。

---

## V100 环境（毕设 PointNet2 / arknights 训练）

### PointNet2 CUDA 算子编译失败（V100 sm_70，上线第一优先级）

> 这是**毕设项目（SUN RGB-D / VoteNet + YOLOv8n）**的 CUDA 算子，不属于 arknights LLM
> 训练栈；建议用**独立 conda 环境**（毕设：Python3.8 + PyTorch1.13.1+CUDA11.7），
> 与本项目 arknights 环境隔离，避免 CUDA/gcc 版本互相污染。PointNet2 是整条 V100
> 上线链路上最易卡点，务必第一步先编译通过，再做其他训练。

以 `pointnet2_ops`（Pointnet2_PyTorch 的算子包）为例，关键是**算力、CUDA、gcc 三者对齐**：

1. **算力显式指定为 7.0（V100 = sm_70）**，不要让它默认编成一堆不匹配的 arch：
   ```bash
   export TORCH_CUDA_ARCH_LIST="7.0"
   ```
   - 报错 `nvcc fatal: Unsupported gpu architecture 'compute_XX'` / `no kernel image
     available`：多是 arch list 与本机 nvcc 不符；V100 固定 `7.0` 即可。

2. **nvcc 与 torch 的 CUDA 版本对齐到 11.7**（PyTorch 1.13.1+cu117）：
   ```bash
   nvcc --version            # 应为 release 11.7
   python -c "import torch;print(torch.version.cuda)"   # 应为 11.7
   echo $CUDA_HOME           # 指向 /usr/local/cuda-11.7
   ```
   - 两者不一致会出现链接期 `undefined symbol / undefined reference`、或运行期版本符号错误。

3. **gcc 版本**：CUDA 11.7 官方支持到 gcc 11；Ubuntu 22.04 默认 gcc-11 一般可用，
   若报一堆模板/语法错，降到 gcc-10 再编译：
   ```bash
   sudo apt install gcc-10 g++-10
   export CC=gcc-10 CXX=g++-10
   ```

4. **老 API 报错（`AT_CHECK`/`THC`、`thrust`、`cudaEvent_t` 等）**：
   用的是没跟上新 torch 的旧 fork。改用仍在维护、兼容 PyTorch1.13 的 `pointnet2_ops`
   版本；这类报错是源码 API 问题，**不是**换 CUDA 能解决的，别在环境变量上反复试。

5. 编译安装并做最小验证：
   ```bash
   pip install -e pointnet2_ops          # 在该算子包目录内
   python - <<'PY'
   import torch, pointnet2_ops
   from pointnet2_ops import pointnet2_utils as u
   x = torch.randn(2, 1024, 3).cuda()
   idx = u.furthest_point_sample(x, 64)   # 能跑通即算子/CUDA 链路正常
   print(idx.shape, idx.device)
   PY
   ```
   - 能 import 但调用报 `no kernel image available`：回到第 1 步检查 arch=7.0 是否真的生效
     （重编时确认 `TORCH_CUDA_ARCH_LIST` 在 pip 编译进程内可见，必要时清掉 build/ 缓存
     `rm -rf build *.egg-info` 后重装）。

- **经验**：先在独立 env 里只装 torch1.13.1+cu117 + pointnet2_ops 把上面的最小样例跑通，
  再装其余依赖；不要在堆满包的环境里定位 CUDA 问题。编译日志先看第一条 `error`，
  后面的大多是连锁报错。

---

（后续批次的问题继续按"现象 / 原因 / 修复 / 经验"追加。）
