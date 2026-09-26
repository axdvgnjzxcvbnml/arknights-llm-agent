import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { EvidenceBadge, EvidenceList, levelLabel } from "@/components/EvidenceBadge"
import type { EvidenceLevel } from "@/types"

describe("EvidenceBadge", () => {
  const allLevels: EvidenceLevel[] = [
    "fact", "retrieved", "inferred", "estimated", "cv", "vlm", "mock",
  ]

  it("7 档 evidence 都能渲染对应中文标签", () => {
    for (const level of allLevels) {
      const { unmount } = render(<EvidenceBadge level={level} source="" />)
      expect(screen.getByText(levelLabel(level))).toBeInTheDocument()
      unmount()
    }
  })

  it("fact/cv 用实线边框，retrieved/inferred/estimated 用虚线边框", () => {
    const { container: factContainer } = render(<EvidenceBadge level="fact" source="" />)
    expect(factContainer.querySelector(".border-solid")).toBeInTheDocument()

    const { container: retContainer } = render(<EvidenceBadge level="retrieved" source="" />)
    expect(retContainer.querySelector(".border-dashed")).toBeInTheDocument()

    const { container: infContainer } = render(<EvidenceBadge level="inferred" source="" />)
    expect(infContainer.querySelector(".border-dashed")).toBeInTheDocument()

    const { container: estContainer } = render(<EvidenceBadge level="estimated" source="" />)
    expect(estContainer.querySelector(".border-dashed")).toBeInTheDocument()
  })

  it("source 非空时显示来源文本", () => {
    render(<EvidenceBadge level="retrieved" source="PRTS:能天使" />)
    expect(screen.getByText("PRTS:能天使")).toBeInTheDocument()
  })

  it("source 为空时不显示来源", () => {
    const { container } = render(<EvidenceBadge level="fact" source="" />)
    // 只有标签文本，没有额外的 source span
    expect(container.textContent).toBe("事实")
  })

  it("未知 level 回退到 mock 样式", () => {
    // @ts-expect-error 测试非法 level 的回退
    const { container } = render(<EvidenceBadge level="unknown_level" source="" />)
    expect(container.querySelector(".bg-slate-500\\/15")).toBeInTheDocument()
  })

  it("title 属性包含 source（悬停提示）", () => {
    const { container } = render(<EvidenceBadge level="fact" source="PRTS页面" />)
    const span = container.querySelector("span")
    expect(span).toHaveAttribute("title", "PRTS页面")
  })
})

describe("EvidenceList", () => {
  it("空列表显示'无引用'", () => {
    render(<EvidenceList items={[]} />)
    expect(screen.getByText("无引用")).toBeInTheDocument()
  })

  it("多个证据渲染多个 badge", () => {
    render(
      <EvidenceList
        items={[
          { level: "fact", source: "PRTS" },
          { level: "inferred", source: "规则推导" },
          { level: "retrieved", source: "RAG" },
        ]}
      />,
    )
    expect(screen.getByText("事实")).toBeInTheDocument()
    expect(screen.getByText("推断")).toBeInTheDocument()
    expect(screen.getByText("检索")).toBeInTheDocument()
  })
})

describe("levelLabel", () => {
  it("返回各档中文标签", () => {
    expect(levelLabel("fact")).toBe("事实")
    expect(levelLabel("retrieved")).toBe("检索")
    expect(levelLabel("inferred")).toBe("推断")
    expect(levelLabel("estimated")).toBe("估算")
    expect(levelLabel("cv")).toBe("CV确认")
    expect(levelLabel("vlm")).toBe("VLM观点")
    expect(levelLabel("mock")).toBe("MOCK")
  })

  it("未知 level 返回原值", () => {
    // @ts-expect-error 测试非法 level
    expect(levelLabel("unknown")).toBe("unknown")
  })
})
