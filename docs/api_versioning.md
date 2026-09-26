# API 版本化与兼容性策略

> 最后更新：2026-09-27

## 一、现状

当前所有 API 接口均无版本前缀，统一使用 `/api/xxx`：

```
GET /api/operator/{name}
GET /api/enemy/{name}
GET /api/stage/{stage_id}
GET /api/search?q=xxx
GET /api/recommend/{stage_id}
GET /api/episode/{id}
GET /api/graph/overview
GET /api/health
GET /api/resources/source-stone
GET /api/training/runs
WS  /ws/live
```

共 17+ 个接口，均为 v0（未版本化）。

## 二、问题

1. **无版本前缀**：未来如果有 breaking change，无法兼容旧客户端
2. **前端硬编码路径**：frontend/ 和 web-kb/ 的 client.ts 直接写 `/api/operator/` 等路径
3. **无 deprecation 机制**：接口变更时无法通知客户端

## 三、评估方案

### 方案 A：加 `/api/v1/` 前缀（推荐）

```
GET /api/v1/operator/{name}
GET /api/v1/enemy/{name}
...
```

- 优点：标准做法，未来 v2 可以并行
- 缺点：需要改所有前端代码，加 redirect 兼容旧路径
- 工作量：约 2 小时（后端加路由别名 + 前端改路径 + 测试）

### 方案 B：保持无版本，用 Header 区分

```
GET /api/operator/{name}
X-API-Version: v1
```

- 优点：不需要改路径
- 缺点：非标准，客户端容易忘记传 Header，调试困难
- 工作量：约 1 小时

### 方案 C：保持现状，变更时加新接口

- 优点：零工作量
- 缺点：接口会越来越多，命名混乱（`/api/operator_v2`）
- 适用：项目早期，接口不稳定

## 四、建议

**当前阶段（CPU 侧骨架）：保持方案 C（无版本）**，理由：
1. 接口还在快速迭代，加版本前缀会增加改动成本
2. 前端只有 2 个（frontend/ + web-kb/），都在本仓库，改路径方便
3. 没有外部消费者，不需要向后兼容

**V100 上线后（接口稳定）：迁移到方案 A（/api/v1/）**，触发条件：
1. 第一个外部消费者出现（非本仓库前端）
2. 接口数量超过 30 个
3. 第一次 breaking change（返回格式变更、字段重命名）

## 五、迁移计划（V100 后执行）

1. 后端：所有路由加 `/api/v1/` 前缀，旧路径加 301 redirect（6 个月过渡期）
2. 前端：client.ts 的 `BASE_URL` 从 `/api` 改为 `/api/v1`
3. 文档：docs/api.md 加版本说明
4. CI：加接口兼容性测试（旧路径返回 301）
5. 6 个月后：删除旧路径 redirect

## 六、Breaking Change 定义

以下变更视为 breaking change，需要升版本：
- 删除接口
- 删除/重命名返回字段
- 改变字段类型
- 改变默认参数值
- 改变 HTTP 状态码

以下变更不视为 breaking change：
- 新增接口
- 新增返回字段（可选）
- 修复 bug（行为从错误变为正确）
- 性能优化

## 七、Deprecation 策略

1. 接口标记 deprecated：在 OpenAPI 文档加 `deprecated: true`
2. 返回 Header 加 `Deprecation: true` 和 `Sunset: <date>`
3. 日志记录 deprecated 接口的调用（WARNING 级别）
4. 至少 3 个月过渡期后删除
