import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import EvidenceBadge from '@/components/replay/EvidenceBadge'
import { EVIDENCE_LEVELS, evidenceChipStyle, evidenceLevel, readingSourceToLevel, spawnSourceToLevel } from '@/constants/evidence'

const NON_FACT = ['retrieved', 'inferred', 'estimated']

describe('证据分级彩色标签', () => {
  it('7 档分级都能渲染出对应英文标签', () => {
    expect(EVIDENCE_LEVELS.map((l) => l.key)).toEqual(
      ['fact', 'annotated', 'cv', 'retrieved', 'inferred', 'estimated', 'mock'],
    )
    for (const lv of EVIDENCE_LEVELS) {
      const { container } = render(<EvidenceBadge level={lv.key} />)
      expect(container.textContent).toContain(lv.key)
    }
  })

  it('非事实级（retrieved/inferred/estimated）用虚线边框，事实级不用', () => {
    for (const lv of EVIDENCE_LEVELS) {
      const { container } = render(<EvidenceBadge level={lv.key} />)
      const el = container.querySelector('span.chip') as HTMLElement
      const dashed = el.style.borderStyle === 'dashed'
      expect(NON_FACT.includes(lv.key) ? dashed : !dashed).toBe(true)
    }
  })

  it('solid 模式实心填充且不虚线', () => {
    const { container } = render(<EvidenceBadge level="fact" solid />)
    const el = container.querySelector('span.chip') as HTMLElement
    expect(el.style.backgroundColor).toBe('rgb(52, 211, 153)')
    expect(el.style.borderStyle).not.toBe('dashed')
  })

  it('tooltip 里带中文名、可信度与释义（防止把推断当事实）', () => {
    const { container } = render(<EvidenceBadge level="estimated" />)
    const title = (container.querySelector('span.chip') as HTMLElement).getAttribute('title') || ''
    expect(title).toContain('均匀估算')
    expect(title).toContain('低')
    expect(title).toContain('校准前勿据此做高风险决策')
  })

  it('showCn 追加中文名；children 可覆盖标签文本', () => {
    const { container } = render(<EvidenceBadge level="cv" showCn />)
    expect(container.textContent).toContain('视觉确认')
    const { container: c2 } = render(<EvidenceBadge level="cv">custom</EvidenceBadge>)
    expect(c2.textContent).toContain('custom')
  })

  it('未知/缺失 level 回落成 unknown，且保留原始字符串便于排查', () => {
    const { container } = render(<EvidenceBadge level="brand-new-level" />)
    expect(container.textContent).toContain('brand-new-level')
    expect(evidenceLevel(undefined).key).toBe('unknown')
    expect(evidenceLevel('nope').label).toBe('nope')
  })
})

describe('来源 -> 证据分级映射', () => {
  it('波次来源：timer:estimated/timer:annotated/vlm 分别映射到 estimated/annotated/inferred', () => {
    expect(spawnSourceToLevel('timer:estimated')).toBe('estimated')
    expect(spawnSourceToLevel('timer:annotated')).toBe('annotated')
    expect(spawnSourceToLevel('vlm')).toBe('inferred')
    expect(spawnSourceToLevel('cv')).toBe('cv')
    expect(spawnSourceToLevel(undefined)).toBe('mock')
  })

  it('读数来源：manual 视为人工标注，其余原样', () => {
    expect(readingSourceToLevel('manual')).toBe('annotated')
    expect(readingSourceToLevel('cv')).toBe('cv')
    expect(readingSourceToLevel('')).toBe('mock')
  })

  it('chip 样式对每档都给出可读的颜色三元组', () => {
    for (const lv of EVIDENCE_LEVELS) {
      const s = evidenceChipStyle(lv.key)
      expect(s.color).toBe(lv.color)
      expect(String(s.backgroundColor)).toMatch(/^rgba\(/)
      expect(String(s.borderColor)).toMatch(/^rgba\(/)
    }
  })
})
