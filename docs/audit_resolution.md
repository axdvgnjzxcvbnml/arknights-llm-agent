# 审计高危问题修复记录

> 日期：2026-09-30
> 审计来源：WorkBuddy 代码审计报告（Kimi 转交）
> 状态：3 项高危全部已修复，无需额外操作

---

## 修复总览

| 编号 | 问题 | 严重度 | 修复 commit | 状态 |
|------|------|--------|-------------|------|
| H1 | `.gitignore` 缺 `data/video_*/` | 高危 | `967a233` | ✅ 已修复 |
| H2 | `configs/agent.yaml` 的 `dtype=bfloat16` | 高危 | `967a233` | ✅ 已修复 |
| H3 | `build_rag.py` 的 batch_size 步长/切片不一致 | 高危 | `967a233` | ✅ 已修复 |

**修复 commit：`967a233`** — "fix: WorkBuddy 审计 3高4中3低修复（H1/H2/H3/M4/M5/M7/M2/L2/L3/L7）"

---

## H1：`.gitignore` 缺 `data/video_*/`

### 问题描述

第十四批新增 `video_extract/` 模块后，视频原始文件和抽帧图片存放在 `data/video_raw/` 和 `data/video_frames/`。虽然这两个具体目录已在 `.gitignore` 中，但缺少通配规则兜底——如果未来新增 `data/video_something/` 目录，可能被误提交到 git。

### 修复内容

在 `.gitignore` 中增加通配规则：

```gitignore
# 通配规则兜底任何 data/video_* 目录（video_raw/video_frames 及未来新增）
data/video_*/
```

### 验证

- `data/video_raw/`、`data/video_frames/` 均被正确忽略
- 未来新增的 `data/video_*/` 目录自动被忽略
- 无视频文件被 git 跟踪

---

## H2：`configs/agent.yaml` 的 `dtype=bfloat16`

### 问题描述

`configs/agent.yaml` 中 slow_thinker 和 fast_reactor 的 dtype 配置为 `bfloat16`。但 V100 显卡（sm_70 架构）**不支持 bf16 张量核**，使用 bf16 会导致：
- 推理时回退到 FP32（性能下降）
- 或直接报错（取决于 PyTorch 版本）
- 与 V100 硬件不兼容

### 修复内容

`configs/agent.yaml` 中两处 `dtype` 从 `bfloat16` 改为 `float16`：

```yaml
slow_thinker:
  dtype: float16  # V100(sm_70) 无 bf16 张量核，统一 fp16

fast_reactor:
  dtype: float16  # V100(sm_70) 无 bf16 张量核，统一 fp16
```

同步修改 `agent/slow_thinker.py` 和 `agent/fast_reactor.py` 的报错文案，明确提示 V100 不支持 bf16。

### 验证

- `configs/agent.yaml` 中无 `bfloat16`
- `agent/slow_thinker.py`、`agent/fast_reactor.py` 报错文案已更新
- V100(sm_70) 上 fp16 可正常运行

---

## H3：`build_rag.py` 的 batch_size 步长/切片不一致

### 问题描述

`knowledge/rag/build_rag.py` 中向量化批次处理存在不一致：
- **循环步长**：使用配置文件中的 `batch_size`（默认 32）
- **切片大小**：硬编码为 32

如果用户在配置中修改了 `batch_size`（如改为 64），循环步长会变成 64，但切片仍然只取 32 个，导致：
- 每个 batch 只处理前 32 个，后 32 个被跳过
- 部分 chunk 未被向量化，检索时缺失
- 静默错误，无报错提示

### 修复内容

提取 `bs` 变量，循环步长和切片统一使用：

```python
# 修复前
for start in range(0, len(texts), int(rag_cfg.get("embedding", {}).get("batch_size", 32))):
    batch = texts[start:start+32]  # 硬编码 32，与步长不一致

# 修复后
bs = int(rag_cfg.get("embedding", {}).get("batch_size", 32))  # 步长与切片统一用 bs
for start in range(0, len(texts), bs):
    batch = texts[start:start+bs]  # 统一用 bs
```

### 验证

- 新增 `tests/test_build_rag_batch.py`（4 个用例），验证不同 batch_size 下步长和切片一致
- 全量 RAG 构建后 chunk 数与输入数一致（无遗漏）
- 检索测试 5 条 query 全部通过

---

## 同 commit 修复的其他问题（中/低危）

commit `967a233` 同时修复了以下中/低危问题（供参考）：

| 编号 | 问题 | 严重度 |
|------|------|--------|
| M4 | `decision_loop.py` 缺 `main()` 入口 | 中 |
| M5 | CI 缺 pytest job | 中 |
| M7 | JSON 读取缺 `with-open` 和坏文件处理 | 中 |
| M2 | `architecture.md` 三处过时内容 | 中 |
| L2 | MCP `_BaseOut.evidence` 非必填 | 低 |
| L3 | `state_to_text` manual 分桶错误 | 低 |
| L7 | `slow_thinker` `_CASTER` 重复 | 低 |

---

## 回归验证

commit `967a233` 提交时的回归结果：

- 单元测试：278 passed / 2 skipped
- 冒烟测试：`run_smoke.sh` 四段全过
- Python 3.8 语法检查：100 个 py 文件全部通过
- 无回归问题

---

## 结论

WorkBuddy 审计报告的 3 项高危问题（H1/H2/H3）全部在 commit `967a233` 中修复，修复方式正确，回归验证通过。**无需额外操作，标记为已完成。**
