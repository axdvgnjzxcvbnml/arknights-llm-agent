import type { ReactNode } from 'react'
import { evidenceChipStyle, evidenceLevel } from '@/constants/evidence'

export interface EvidenceBadgeProps {
  /** 证据分级键；未知值会回落成灰色 unknown 徽章 */
  level?: string | null
  children?: ReactNode
  solid?: boolean
  /** 是否在英文标签后再显示中文名 */
  showCn?: boolean
  title?: string
}

/**
 * 证据分级彩色标签（回放页统一入口）。
 * retrieved / inferred / estimated 这类"非事实"级别额外加虚线边框，视觉上就和
 * fact / cv 区分开 —— 呼应项目里"检索与推断绝不允许被当成确定事实"的约束。
 */
export default function EvidenceBadge({ level, children, solid = false, showCn = false, title }: EvidenceBadgeProps) {
  const meta = evidenceLevel(level)
  const soft = ['retrieved', 'inferred', 'estimated'].includes(meta.key)
  const style = { ...evidenceChipStyle(meta.key, { solid }) }
  if (soft && !solid) style.borderStyle = 'dashed'
  const text = children ?? meta.label
  return (
    <span
      className="chip font-mono"
      style={style}
      title={title || `${meta.label} · ${meta.cn}（${meta.trust}）：${meta.desc}`}
    >
      <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: solid ? '#080b12' : meta.color }} />
      {text}
      {showCn ? <span className="font-sans opacity-75">{meta.cn}</span> : null}
    </span>
  )
}
