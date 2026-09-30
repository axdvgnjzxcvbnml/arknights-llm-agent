/**
 * 知识图谱数据层测试（对应任务 B 的"图谱交互"）。
 *
 * 只测数据契约与空态处理，不测 d3 渲染：后端在图谱未构建时返回 503
 * （Issue #7），前端必须能把它变成可用空态而不是白屏。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const SUBGRAPH = {
  found: true,
  evidence: 'fact',
  stage_id: '3-8',
  stage_title: '3-8 黄昏',
  enemy_count: 2,
  operator_count: 0,
  nodes: [{ node_id: 'stage:3-8', kind: 'stage', name: '黄昏' },
          { node_id: 'enemy:碎骨', kind: 'enemy', name: '碎骨' }],
  edges: [{ source: 'stage:3-8', target: 'enemy:碎骨', relation: 'CONTAINS_ENEMY',
            count: '16', evidence: 'fact' }],
}

function mockFetch(impl: () => Promise<{ ok: boolean; status?: number; body?: unknown }>) {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const r = await impl()
    return { ok: r.ok, status: r.status ?? 200, json: async () => r.body } as Response
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

describe('知识图谱接口（/api/graph/*）', () => {
  beforeEach(() => {
    // 走真实 API 分支（默认 USE_MOCK=true 会去读 public/mock）
    vi.stubEnv('VITE_USE_MOCK', 'false')
    vi.resetModules()
  })
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  async function load() {
    return await import('@/api/endpoints')
  }

  it('关卡子图：snake_case 转 camelCase，evidence 分级原样保留', async () => {
    const fn = mockFetch(async () => ({ ok: true, body: SUBGRAPH }))
    const { getStageSubgraph } = await load()
    const res = await getStageSubgraph('3-8')

    expect(String(fn.mock.calls[0][0])).toContain('/api/graph/subgraph/3-8')
    expect(res).not.toBeNull()
    expect((res as any).enemyCount).toBe(2)
    expect((res as any).stageTitle).toBe('3-8 黄昏')
    expect((res as any).nodes[0].nodeId).toBe('stage:3-8')
    expect((res as any).edges[0].relation).toBe('CONTAINS_ENEMY')
    // fact 级不能被降级成推断（前端据此决定实线/虚线样式）
    expect((res as any).edges[0].evidence).toBe('fact')
  })

  it('found:false 视为业务空态，返回 null 而不抛错', async () => {
    mockFetch(async () => ({ ok: true, body: { found: false, message: '无此关卡' } }))
    const { getStageSubgraph } = await load()
    await expect(getStageSubgraph('99-99')).resolves.toBeNull()
  })

  it('404 也被当成空态（节点/关卡不存在不该让页面崩）', async () => {
    mockFetch(async () => ({ ok: false, status: 404, body: { detail: '未找到关卡子图' } }))
    const { getNodeDetail } = await load()
    await expect(getNodeDetail('operator:不存在的干员')).resolves.toBeNull()
  })

  it('503（图谱未构建）当前会抛错 —— Issue #7 的期望行为是降级空态', async () => {
    mockFetch(async () => ({
      ok: false, status: 503,
      body: { found: false, evidence: 'fact', message: '知识图谱文件缺失；请先运行 scripts/build_graph.sh' },
    }))
    const { getStageSubgraph } = await load()
    // 记录当前实现：只有 404 被吞掉，503 会抛出 -> 调用方必须自己兜底
    await expect(getStageSubgraph('3-8')).rejects.toThrow(/503/)
  })

  it('节点 id 含中文与冒号时做 URL 编码，避免路径被截断', async () => {
    const fn = mockFetch(async () => ({ ok: true, body: { found: true, node_id: 'operator:能天使', neighbors: [] } }))
    const { getNodeDetail } = await load()
    await getNodeDetail('operator:能天使')
    const url = String(fn.mock.calls[0][0])
    expect(url).toContain(encodeURIComponent('operator:能天使'))
    expect(url).not.toContain('能天使')
  })
})
