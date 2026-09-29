// @ts-nocheck
/**
 * 证据分级：颜色 + 释义的**单一事实来源**。
 * 取值与后端 agent/output_schema.py 的 EvidenceLevel 一一对应，新增分级时两边同步。
 *
 * 项目铁律（见 output_schema.py 注释）：
 *   retrieved / inferred 绝不允许被下游当成确定事实 —— 所以界面上这两级用冷色 + 虚线边框，
 *   并在图例里明说"需核实 / 非事实"。
 */
export const EVIDENCE_LEVELS = [
  {
    key: 'fact',
    label: 'fact',
    cn: '结构化事实',
    color: '#34d399',
    trust: '可信',
    desc: 'PRTS Wiki 解析出的结构化事实（关卡面板、干员/敌人属性等）',
  },
  {
    key: 'annotated',
    label: 'annotated',
    cn: '人工标注',
    color: '#2dd4bf',
    trust: '可信',
    desc: '录制/人工标注的数据，例如逐关回填的真实敌人出场时间轴',
  },
  {
    key: 'cv',
    label: 'cv',
    cn: '视觉确认',
    color: '#22d3ee',
    trust: '较可信',
    desc: 'YOLO/OCR 从画面里确认到的读数，可能误识别，带 confidence',
  },
  {
    key: 'retrieved',
    label: 'retrieved',
    cn: '检索参考',
    color: '#60a5fa',
    trust: '需核实',
    desc: 'RAG 检索到的攻略/资料，是参考而非事实判断',
  },
  {
    key: 'inferred',
    label: 'inferred',
    cn: '规则/模型推断',
    color: '#a78bfa',
    trust: '非事实',
    desc: '知识图谱规则或模型（含 VLM 局势判断）推断出的结论，非事实',
  },
  {
    key: 'estimated',
    label: 'estimated',
    cn: '均匀估算',
    color: '#fbbf24',
    trust: '低',
    desc: '按固定间隔均匀估算的值（如敌人出场时刻），校准前勿据此做高风险决策',
  },
  {
    key: 'mock',
    label: 'mock',
    cn: '程序合成',
    color: '#94a3b8',
    trust: '非真实',
    desc: '程序合成数据，不来自真实游戏画面（冒烟链路专用）',
  },
]

const BY_KEY = new Map(EVIDENCE_LEVELS.map((l) => [l.key, l]))

/** 未知分级也要能渲染：给个中性灰，并把原始字符串显示出来 */
export const FALLBACK_LEVEL = {
  key: 'unknown',
  label: 'unknown',
  cn: '未标注',
  color: '#64748b',
  trust: '未知',
  desc: '后端未标注证据级别',
}

export function evidenceLevel(key) {
  if (!key) return FALLBACK_LEVEL
  const k = String(key).trim().toLowerCase()
  return BY_KEY.get(k) || { ...FALLBACK_LEVEL, label: k, key: k }
}

/**
 * 波次来源（perception.schemas.SpawnSource）映射到证据分级：
 *   timer:estimated -> estimated / timer:annotated -> annotated / vlm -> inferred
 */
export function spawnSourceToLevel(source) {
  const s = String(source || '').toLowerCase()
  if (s === 'timer:estimated') return 'estimated'
  if (s === 'timer:annotated') return 'annotated'
  if (s === 'vlm') return 'inferred'
  return s || 'mock'
}

/** 读数来源（cv / mock / manual）映射到证据分级 */
export function readingSourceToLevel(source) {
  const s = String(source || '').toLowerCase()
  if (s === 'manual') return 'annotated'
  return s || 'mock'
}

function hexToRgba(hex, alpha) {
  const h = hex.replace('#', '')
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
  const int = parseInt(full, 16)
  const r = (int >> 16) & 255
  const g = (int >> 8) & 255
  const b = int & 255
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

/**
 * 徽章样式：用内联 style 而不是 Tailwind 动态类名，
 * 避免 JIT 扫不到 `bg-ev-${level}` 这种拼接类而被 purge 掉。
 */
export function evidenceChipStyle(key, { solid = false } = {}) {
  const { color } = evidenceLevel(key)
  return solid
    ? { backgroundColor: color, color: '#080b12', borderColor: color }
    : {
        color,
        backgroundColor: hexToRgba(color, 0.12),
        borderColor: hexToRgba(color, 0.42),
      }
}

export function evidenceDotStyle(key) {
  return { backgroundColor: evidenceLevel(key).color }
}

export function evidenceLineStyle(key) {
  return { backgroundColor: evidenceLevel(key).color, boxShadow: `0 0 8px ${hexToRgba(evidenceLevel(key).color, 0.55)}` }
}
