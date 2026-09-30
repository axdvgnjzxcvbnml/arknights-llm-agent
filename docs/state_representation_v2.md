# Stage 2 双通道状态表示设计

> 日期：2026-09-30
> 状态：已实现（schema + 张量转换 + 动作空间 + 单元测试）
> 相关文件：`perception/schemas.py`、`perception/state_tensor.py`、`perception/action_space_v2.py`、`perception/state_to_text.py`

---

## 1. 为什么需要双通道

当前 `perception/state_to_text.py` 只输出**文本通道**（给 LLM 做推理），但"无作业推关"的核心——搜索/规划层——需要**结构化数值张量**：

| 通道 | 消费者 | 数据形态 | 优势 | 局限 |
|------|--------|----------|------|------|
| 文本通道 | LLM（慢思考） | 自然语言字符串 | 语义丰富、可解释 | 不可微、不可批量、搜索效率低 |
| 张量通道 | 搜索/CNN/规划层 | 固定尺寸数值数组 | 可批量、可向量化、搜索效率高 | 语义抽象、需编码设计 |

**双通道对应同一 GameState，信息对齐**：LLM 用文本做推理，搜索层用张量做数值计算，两者共享同一状态源。

---

## 2. 张量通道设计

### 2.1 维度常量

所有张量**固定尺寸**，不足零填充，超出裁剪，便于批量处理和 CNN 输入。

| 常量 | 值 | 说明 |
|------|-----|------|
| `MAP_H` | 10 | 地图行数 |
| `MAP_W` | 10 | 地图列数 |
| `MAP_C` | 4 | 地图通道数 |
| `MAX_ENEMIES` | 20 | 最大同时在场敌人数 |
| `ENEMY_F` | 6 | 敌人特征数 |
| `MAX_OPERATORS` | 12 | 最大可用干员数（手牌） |
| `OPERATOR_F` | 6 | 干员特征数 |
| `MAX_DEPLOYED` | 8 | 最大已部署干员数 |
| `DEPLOYED_F` | 5 | 已部署干员特征数 |

### 2.2 地图张量 `MapTensor`：10×10×4

```
shape: [MAP_H, MAP_W, MAP_C] = [10, 10, 4]
```

| 通道 | 含义 | 取值 |
|------|------|------|
| c=0 | 可部署 | 1=可部署且未占用，0=不可部署或已占用 |
| c=1 | 已占用 | 1=已有干员部署，0=空 |
| c=2 | 地面 | 1=terrain=ground，0=非地面 |
| c=3 | 高台 | 1=terrain=highland，0=非高台 |

**存储方式**：扁平化一维数组，行优先 `data[h*W*C + w*C + c]`。

**使用场景**：
- CNN 输入：直接 reshape 为 (1, 4, 10, 10)
- 搜索层：遍历 c=0 通道找可部署格子
- 部署合法性检查：c=0[col,row] == 1

### 2.3 敌人张量 `EnemyTensor`：20×6

```
shape: [MAX_ENEMIES, ENEMY_F] = [20, 6]
valid_count: 实际有效敌人数（非 padding）
```

| 特征索引 | 含义 | 取值 |
|----------|------|------|
| f=0 | 位置 col | 0~9，从 position_hint 推断 |
| f=1 | 位置 row | 0~9 |
| f=2 | 血量比例 | 0~1，无法读取默认 1.0（满血） |
| f=3 | 速度 | 默认 1.0，V100 视觉检测后填真实值 |
| f=4 | 类型编码 | 名称哈希取模 100，V100 后可改为分类 one-hot |
| f=5 | 数量 | observed_count |

**padding**：不足 20 个的部分全零，`valid_count` 标记有效数量。

### 2.4 干员张量 `OperatorTensor`：12×6

```
shape: [MAX_OPERATORS, OPERATOR_F] = [12, 6]
```

| 特征索引 | 含义 | 取值 |
|----------|------|------|
| f=0 | 费用 | cost |
| f=1 | 攻击范围编码 | 0=近战，1=远程（按职业推断） |
| f=2 | 冷却 | 手牌中未部署默认 0 |
| f=3 | 职业编码 | 先锋=1, 近卫=2, 狙击=3, 术师=4, 重装=5, 医疗=6, 辅助=7, 特种=8, 召唤=9 |
| f=4 | 是否可用 | 1=available，0=不可用 |
| f=5 | 精英等级 | elite |

### 2.5 已部署张量 `DeployedTensor`：8×5

```
shape: [MAX_DEPLOYED, DEPLOYED_F] = [8, 5]
```

| 特征索引 | 含义 | 取值 |
|----------|------|------|
| f=0 | 位置 col | 从 cell_id 解析 |
| f=1 | 位置 row | 从 cell_id 解析 |
| f=2 | 朝向编码 | up=0, down=1, left=2, right=3 |
| f=3 | 血量比例 | hp_ratio，None 默认 1.0 |
| f=4 | 职业编码 | 从名称匹配 operator_cards |

### 2.6 标量状态 `ScalarState`

| 字段 | 含义 |
|------|------|
| cost | 当前费用 |
| life_points | 目标点耐久 |
| deploy_used | 已部署数 |
| deploy_limit | 部署上限 |
| timestamp | 游戏时间（秒） |
| cost_state | 费用读数状态：0=ok, 1=uncertain, 2=missing |

---

## 3. 形式化动作空间

### 3.1 动作类型

| 动作 | 参数 | 说明 |
|------|------|------|
| `DeployAction` | operator_idx, grid_col, grid_row, direction | 部署干员 |
| `SkillAction` | deployed_idx | 开启技能 |
| `RetreatAction` | deployed_idx | 撤退干员 |
| `WaitAction` | （无） | 等待（不操作） |

### 3.2 合法性约束

- **deploy**：干员可用（费用够）、格子可部署且未占用、干员未已部署
- **skill**：已部署干员存在（第一版不检查冷却，V100 后加精细判断）
- **retreat**：已部署干员存在
- **wait**：恒合法

### 3.3 枚举顺序

动作在 `ActionSpaceV2.actions` 列表中的顺序：
```
deploy_actions → skill_actions → retreat_actions → wait_action
```

可通过 `deploy_count`、`skill_count`、`retreat_count` 定位各类型的起始索引。

### 3.4 空间大小估算

`estimate_space_size(state)` 不实际生成动作，直接估算：

```
deploy = (可用干员数 - 已部署数) × 可部署格子数 × 4（朝向）
skill = 已部署数
retreat = 已部署数
wait = 1
total = deploy + skill + retreat + 1
```

**典型场景**：3-8 关卡，3 个可用干员（1 已部署），99 个可部署格子：
- deploy = 2 × 99 × 4 = 792
- skill = 1, retreat = 1, wait = 1
- total = 795

搜索层可以直接遍历这 795 个动作，评估每个动作的价值。

---

## 4. 文本通道与张量通道的一致性

`check_alignment(state)` 函数验证双通道信息对齐：

| 检查项 | 验证内容 |
|--------|----------|
| cost | 张量 scalars.cost == GameState.cost.current |
| life | 张量 scalars.life_points == GameState.life_points |
| operator_count | 张量 valid_count == len(operator_cards) |
| enemy_count | 张量 valid_count == len(enemies_on_field) |
| map_nonempty | 地图张量有非零值（当 game_map 非空时） |
| text_nonempty | 文本通道输出非空 |

**设计原则**：双通道从同一 GameState 生成，信息必须对齐。如果某维度不对齐，说明转换逻辑有 bug。

---

## 5. 搜索层如何使用张量通道

> 本节描述搜索层的使用方式，**搜索算法本身不在本批实现范围内**。

### 5.1 状态评估

搜索层拿到 `StateTensor` 后，可以：
1. 用 CNN 处理地图张量（10×10×4），提取空间特征
2. 用 MLP 处理敌人/干员/已部署张量，提取单位特征
3. 拼接标量状态，输出状态价值 V(s)

### 5.2 动作评估

对 `ActionSpaceV2` 中的每个动作：
1. 模拟动作执行（部署/技能/撤退），得到新状态
2. 用状态评估函数 V(s') 评估新状态
3. 选择 argmax V(s') 的动作

### 5.3 与 LLM 的协作

- **快通道**：搜索层用张量做快速评估（目标 <50ms），输出候选动作
- **慢通道**：LLM 用文本做深度推理（目标 1-2s），输出 reasoning + 最终决策
- 搜索层的候选动作可以作为 LLM 的"选项"，LLM 从中选择并给出理由

---

## 6. 已知局限与未来改进

| 局限 | 当前处理 | 未来改进 |
|------|----------|----------|
| 敌人位置从 position_hint 推断（粗粒度） | 左侧/右侧/中间三档 | V100 视觉检测后填精确坐标 |
| 敌人速度/血量默认值 | speed=1.0, hp=1.0 | V100 视觉检测后填真实值 |
| 敌人类型用名称哈希 | hash % 100 | 改为 PRTS 敌人分类 one-hot |
| 干员攻击范围按职业推断 | 近战=0, 远程=1 | 改为 PRTS 干员攻击范围数据 |
| 技能动作不检查冷却 | 所有已部署干员可开技能 | V100 后加冷却状态检测 |
| 地图固定 10×10 | 不足 padding，超出裁剪 | 支持动态尺寸（需要 CNN 适配） |

---

## 7. 文件清单

| 文件 | 内容 |
|------|------|
| `perception/schemas.py` | Pydantic 模型：StateTensor/MapTensor/EnemyTensor/OperatorTensor/DeployedTensor/ScalarState/ActionSpaceV2/4种Action + 维度常量 |
| `perception/state_tensor.py` | GameState → StateTensor 转换实现 + 各张量构建函数 + 一致性检查 |
| `perception/action_space_v2.py` | 形式化动作空间枚举 + 合法性约束 + 空间大小估算 + 动作描述 |
| `perception/state_to_text.py` | 文本通道（已有，未修改） |
| `tests/test_state_tensor.py` | 39 个单元测试：地图/敌人/干员/已部署/标量/完整转换/动作空间/一致性/边界 |

---

## 8. 测试覆盖

39 个单元测试，覆盖：

- **地图张量**（6）：shape、可部署通道、已占用通道、地形通道、None 地图、越界裁剪
- **敌人张量**（4）：shape/数量、特征值、padding、空敌人
- **干员张量**（3）：shape/数量、特征值（费用/范围/职业/可用性）、padding
- **已部署张量**（2）：shape/数量、特征值（位置/朝向/血量）
- **标量状态**（3）：基本值、uncertain 费用、missing 费用
- **完整转换**（2）：丰富状态、空状态
- **动作空间**（8）：可枚举、wait 恒有、部署合法性、技能动作、撤退动作、已部署不可重复部署、空间大小估算、动作描述
- **一致性**（6）：费用/生命/干员数/敌人数/文本非空/全维度对齐
- **边界**（5）：空状态、超量干员裁剪、超量敌人裁剪、None 费用、无效 cell_id

**测试结果**：39 passed in 0.42s
