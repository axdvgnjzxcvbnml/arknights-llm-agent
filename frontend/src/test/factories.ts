/** 测试用 DTO 工厂：字段与 src/types/episode.ts 对齐，只填渲染必需的最小集合。 */
import type { Action, EvidenceRef, StepDto, EpisodeDto } from '@/types/episode'

export function makeAction(over: Partial<Action> = {}): Action {
  return { action: 'deploy', operatorId: '翎羽', gridPos: 'A1', direction: 'left', ...over }
}

export function makeStep(over: Partial<StepDto> = {}): StepDto {
  const n = over.step ?? 1
  return {
    index: n - 1,
    step: n,
    elapsedSec: n,
    state: {
      stageId: '3-8', timingSource: 'estimated',
      cost: { current: 6 + n, limit: 99, confidence: 1, source: 'mock', state: 'ok' },
      lifePoints: 3, deployUsed: n, deployLimit: 9,
      operatorCards: [], deployed: [], skills: [],
      enemiesOnField: [{ name: '源石虫', observedCount: 3, positionHint: '左侧', source: 'cv' }],
      spawnPlan: [], occupiedCells: [], notes: [], vlm: null, stateText: '【关卡】3-8',
    },
    knowledge: { query: 'q', contextText: 'ctx', citations: [] },
    reasoning: { summary: `部署 翎羽 到 A${n}`, analysis: ['费用足够'], consideredActions: [], risks: [] },
    decision: {
      confidence: 0.55, thinker: 'mock', thoughtMs: 0.1,
      plan: { actions: [makeAction({ gridPos: `A${n}` })] },
    },
    bridge: null, command: null,
    execute: {
      total: 1, succeeded: 1, failed: 0, completed: true,
      results: [{ index: 0, action: 'deploy', success: true, status: 'ok', error: '', ops: ['tap', 'wait'] }],
    },
    reflection: null,
    after: { cost: 7 + n, life: 3 },
    reward: { stepReward: 0, items: [] },
    evidence: [{ level: 'retrieved', source: 'PRTS攻略(mock)' }] as EvidenceRef[],
    latencyMs: { slowMs: 0.1, executeMs: 0.2 },
    ...over,
  }
}

export function makeSteps(n: number): StepDto[] {
  return Array.from({ length: n }, (_, i) => makeStep({ step: i + 1 }))
}

export function makeEpisode(over: Partial<EpisodeDto> = {}): EpisodeDto {
  return {
    id: 'ep-3-8-win', title: '3-8 通关局', stageId: '3-8', backend: 'mock',
    outcome: 'win', outcomeLabel: '通关', stepCount: 10, durationSec: 0.1, gameTimeSec: 10,
    reward: {
      total: 100, winBonus: 100, leakPenalty: 0, overcostPenalty: 0, leaked: 0,
      overcostSec: 0, lifeStart: 3, lifeEnd: 3, summaryLine: '总分 100', items: [],
    },
    totals: { actionsTotal: 10, actionsSucceeded: 10, actionsFailed: 0, avgConfidence: 0.5, latencySumMs: {} },
    map: { cols: 2, rows: 1, cells: [
      { cellId: 'A1', col: 0, row: 0, terrain: 'ground', deployable: true },
      { cellId: 'B1', col: 1, row: 0, terrain: 'blocked', deployable: false },
    ] },
    ...over,
  }
}
