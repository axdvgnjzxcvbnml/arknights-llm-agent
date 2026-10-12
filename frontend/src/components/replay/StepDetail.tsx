import StatePanel from './StatePanel'
import MapGrid from './MapGrid'
import OperatorRoster from './OperatorRoster'
import EnemyPanel from './EnemyPanel'
import ReasoningPanel from './ReasoningPanel'
import KnowledgePanel from './KnowledgePanel'
import ActionPanel from './ActionPanel'
import LatencyPanel from './LatencyPanel'
import ReflectionPanel from './ReflectionPanel'
import { Card } from '@/components/replay/ui'
import type { MapTopology, StepDto } from '@/types/episode'

/** 单步详情：状态 -> 决策理由 -> 知识 -> 动作 -> 耗时 -> 结果，按"看-想-打-解释"的顺序排。 */
export interface StepDetailProps {
  step: StepDto | null
  /** 对局级地图拓扑（Issue #2：API 模式下后端暂未提供，走空态） */
  map?: MapTopology | null
  /** 干员名 -> 职业/费用，用于给已部署干员上色（部署后手牌里就没有它了） */
  roster?: Map<string, { operatorClass?: string; cost?: number }>
}

export default function StepDetail({ step, map, roster }: StepDetailProps) {
  if (!step) return null
  const plan = step.decision?.plan || null

  return (
    <div key={step.step} className="animate-fade-up space-y-3">
      <StatePanel step={step} />

      <div className="grid gap-3 xl:grid-cols-2">
        <MapGrid map={map} step={step} highlightAction={plan} roster={roster} />
        <EnemyPanel step={step} />
      </div>

      <OperatorRoster step={step} roster={roster} />

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <ReasoningPanel step={step} />
        <KnowledgePanel step={step} />
      </div>

      <ActionPanel step={step} />

      <div className="grid gap-3 xl:grid-cols-2">
        <LatencyPanel step={step} />
        <ReflectionPanel step={step} />
      </div>

      <Card title="喂给 LLM 的状态原文（state_text）" bodyClass="p-2">
        <details>
          <summary className="cursor-pointer px-1 py-1 text-[11px] text-slate-500 hover:text-slate-300">
            展开查看逐步渲染的原始状态文本（与 results/agent_decision_log.txt 中「状态（喂给 LLM）」段落一致）
          </summary>
          <pre className="scrollbar-thin mt-2 max-h-[420px] overflow-auto whitespace-pre-wrap rounded-md border border-ink-700/70 bg-ink-950/70 p-3 font-mono text-[11.5px] leading-relaxed text-slate-300">
            {step.state?.stateText || '（无）'}
          </pre>
        </details>
      </Card>
    </div>
  )
}
