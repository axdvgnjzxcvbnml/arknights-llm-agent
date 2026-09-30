import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TimelineRail from '@/components/replay/TimelineRail'
import { makeStep, makeSteps } from '@/test/factories'

function nodes(container: HTMLElement) {
  return container.querySelectorAll('[data-step-idx]')
}

describe('TimelineRail 决策时间轴', () => {
  it('按步数渲染节点，节点里给出步号、对局时间与决策结论', () => {
    const { container, getByText } = render(
      <TimelineRail steps={makeSteps(4)} current={0} onSelect={() => {}} />,
    )
    expect(nodes(container)).toHaveLength(4)
    expect(getByText('t=3s')).toBeTruthy()
    expect(getByText('部署 翎羽 到 A3')).toBeTruthy()
    expect(container.textContent).toContain('4 步')
  })

  it('点击节点回调该步的数组下标（不是步号）', () => {
    const onSelect = vi.fn()
    const { container } = render(
      <TimelineRail steps={makeSteps(5)} current={0} onSelect={onSelect} />,
    )
    fireEvent.click(nodes(container)[3].querySelector('button')!)
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect).toHaveBeenCalledWith(3)
  })

  it('当前步高亮：只有 current 对应节点带 cyan 选中样式', () => {
    const { container, rerender } = render(
      <TimelineRail steps={makeSteps(3)} current={1} onSelect={() => {}} />,
    )
    const btns = () => Array.from(container.querySelectorAll('[data-step-idx] button'))
    expect(btns()[1].className).toContain('border-cyan-400')
    expect(btns()[0].className).not.toContain('border-cyan-400')

    rerender(<TimelineRail steps={makeSteps(3)} current={2} onSelect={() => {}} />)
    expect(btns()[2].className).toContain('border-cyan-400')
    expect(btns()[1].className).not.toContain('border-cyan-400')
  })

  it('动作类型来自执行结果：wait 步显示"等待"，deploy 步显示"部署"', () => {
    const steps = [
      makeStep({ step: 1 }),
      makeStep({
        step: 2,
        execute: {
          total: 1, succeeded: 1, failed: 0, completed: true,
          results: [{ index: 0, action: 'wait', success: true, status: 'ok', error: '', ops: ['wait'] }],
        },
        decision: { confidence: 0.4, thinker: 'mock', thoughtMs: 0.1, plan: { actions: [{ action: 'wait', durationMs: 1000 }] } },
      }),
    ]
    const { container } = render(<TimelineRail steps={steps} current={0} onSelect={() => {}} />)
    const text = nodes(container)[1].textContent || ''
    expect(text).toContain('等待')
    expect(nodes(container)[0].textContent).toContain('部署')
  })

  it('执行失败的步标记 fail，成功的标 ok', () => {
    const steps = [
      makeStep({ step: 1 }),
      makeStep({
        step: 2,
        execute: {
          total: 1, succeeded: 0, failed: 1, completed: true,
          results: [{ index: 0, action: 'deploy', success: false, status: 'offline', error: '设备离线', ops: [] }],
        },
      }),
    ]
    const { container } = render(<TimelineRail steps={steps} current={0} onSelect={() => {}} />)
    expect(nodes(container)[0].textContent).toContain('ok')
    expect(nodes(container)[1].textContent).toContain('fail')
  })

  it('展示当时费用/耐久与本步奖励增量', () => {
    const steps = [makeStep({ step: 1, reward: { stepReward: -10, items: [{ name: 'leak', delta: -10, why: '漏怪' }] } })]
    const { container } = render(<TimelineRail steps={steps} current={0} onSelect={() => {}} />)
    const text = nodes(container)[0].textContent || ''
    expect(text).toContain('费7')      // state.cost.current = 6 + step
    expect(text).toContain('耐3')
    expect(text).toContain('-10')
  })

  it('空 steps 时给出空态而不是崩溃', () => {
    const { getByText } = render(<TimelineRail steps={[]} current={0} onSelect={() => {}} />)
    expect(getByText('暂无步骤数据')).toBeTruthy()
  })
})
