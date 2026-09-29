/** 界面文案与配色常量：动作类型 / 结局 / 反思结论 / 延迟阶段 / 职业。 */

export const ACTION_META = {
  deploy: { cn: '部署', color: '#34d399', icon: '▼', desc: 'operator_id + grid_pos + direction' },
  skill: { cn: '技能', color: '#fbbf24', icon: '✦', desc: 'operator_id + skill_id(1-3)' },
  retreat: { cn: '撤退', color: '#fb7185', icon: '↩', desc: 'operator_id' },
  wait: { cn: '等待', color: '#94a3b8', icon: '⏸', desc: 'duration_ms' },
}

export function actionMeta(type) {
  return ACTION_META[type] || { cn: type || '未知', color: '#64748b', icon: '•', desc: '' }
}

export const OUTCOME_META = {
  win: { cn: '通关', color: '#34d399', badge: 'bg-emerald-400/15 text-emerald-300 border-emerald-400/40' },
  defeat: { cn: '失败', color: '#fb7185', badge: 'bg-rose-400/15 text-rose-300 border-rose-400/40' },
  timeout: { cn: '步数上限', color: '#fbbf24', badge: 'bg-amber-400/15 text-amber-300 border-amber-400/40' },
  aborted: { cn: '中止', color: '#94a3b8', badge: 'bg-slate-400/15 text-slate-300 border-slate-400/40' },
}

export function outcomeMeta(outcome) {
  return OUTCOME_META[outcome] || OUTCOME_META.aborted
}

export const VERDICT_META = {
  good: { cn: '良好', color: '#34d399' },
  risky: { cn: '有风险', color: '#fbbf24' },
  bad: { cn: '失误', color: '#fb7185' },
}

export function verdictMeta(v) {
  return VERDICT_META[v] || { cn: v || '—', color: '#94a3b8' }
}

/** 延迟阶段：顺序即链路顺序（看 -> 想 -> 打），label 对齐后端 latency_ms 的键 */
export const LATENCY_STAGES = [
  { key: 'perceiveMs', cn: '感知', hint: '截屏 + OCR/YOLO + 状态组装', color: '#22d3ee' },
  { key: 'knowledgeMs', cn: '知识检索', hint: 'RAG + 知识图谱', color: '#60a5fa' },
  { key: 'slowMs', cn: '慢思考', hint: 'Qwen3-8B-Thinking 出决策', color: '#a78bfa' },
  { key: 'bridgeMs', cn: '慢快桥接', hint: '隐藏态投影到快反应输入空间', color: '#c084fc' },
  { key: 'fastMs', cn: '快反应', hint: 'MiniCPM 级小模型裁剪即时不可行动作', color: '#f472b6' },
  { key: 'executeMs', cn: '动作执行', hint: 'ADB 原语下发（tap/swipe/wait）', color: '#34d399' },
  { key: 'agentMs', cn: 'Agent 合计', hint: 'think+bridge+react 全链路', color: '#fbbf24' },
  { key: 'stepMs', cn: '本步墙钟', hint: 'env.step 全过程（含感知与奖励结算）', color: '#94a3b8' },
]

/** 干员职业配色（明日方舟职业习惯色，仅用于区分标签） */
export const CLASS_COLORS = {
  先锋: '#fbbf24',
  近卫: '#fb7185',
  重装: '#60a5fa',
  医疗: '#34d399',
  术师: '#a78bfa',
  狙击: '#22d3ee',
  辅助: '#c084fc',
  特种: '#f97316',
}

export function classColor(name) {
  return CLASS_COLORS[name] || '#94a3b8'
}

export const DIRECTION_CN = { up: '上', down: '下', left: '左', right: '右' }
export const DIRECTION_ARROW = { up: '↑', down: '↓', left: '←', right: '→' }

/** 回放速度档位：值 = 每步停留毫秒数的倍率基准 */
export const PLAYBACK_SPEEDS = [
  { label: '0.5×', ms: 2400 },
  { label: '1×', ms: 1200 },
  { label: '2×', ms: 600 },
  { label: '4×', ms: 300 },
]
