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
