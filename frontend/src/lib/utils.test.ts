import { describe, it, expect } from "vitest"
import {
  camelizeKey, deepCamelize, formatDateTime, formatDuration, asPercent, cn,
} from "@/lib/utils"

describe("camelizeKey", () => {
  it("snake_case 转 camelCase", () => {
    expect(camelizeKey("latency_ms_p50")).toBe("latencyMsP50")
    expect(camelizeKey("stage_id")).toBe("stageId")
    expect(camelizeKey("operator_class")).toBe("operatorClass")
  })

  it("kebab-case 转 camelCase", () => {
    expect(camelizeKey("data-source")).toBe("dataSource")
    expect(camelizeKey("x-axis")).toBe("xAxis")
  })

  it("无下划线/连字符的键不变", () => {
    expect(camelizeKey("name")).toBe("name")
    expect(camelizeKey("url")).toBe("url")
  })

  it("数字后缀正常转换", () => {
    expect(camelizeKey("value_1")).toBe("value1")
    expect(camelizeKey("item_2a")).toBe("item2a")
  })
})

describe("deepCamelize", () => {
  it("简单对象键转换", () => {
    const input = { stage_id: "3-8", operator_name: "能天使" }
    expect(deepCamelize(input)).toEqual({ stageId: "3-8", operatorName: "能天使" })
  })

  it("嵌套对象递归转换", () => {
    const input = {
      data: {
        enemy_list: [{ enemy_name: "碎骨", hp_value: 100 }],
        meta_info: { source_url: "http://example.com" },
      },
    }
    const result = deepCamelize(input)
    expect(result).toEqual({
      data: {
        enemyList: [{ enemyName: "碎骨", hpValue: 100 }],
        metaInfo: { sourceUrl: "http://example.com" },
      },
    })
  })

  it("数组递归转换", () => {
    const input = [{ item_id: 1 }, { item_id: 2 }]
    expect(deepCamelize(input)).toEqual([{ itemId: 1 }, { itemId: 2 }])
  })

  it("null/undefined 原样返回", () => {
    expect(deepCamelize(null)).toBeNull()
    expect(deepCamelize(undefined)).toBeUndefined()
  })

  it("原始值（字符串/数字/布尔）原样返回", () => {
    expect(deepCamelize("hello")).toBe("hello")
    expect(deepCamelize(42)).toBe(42)
    expect(deepCamelize(true)).toBe(true)
  })

  it("混合嵌套结构完整转换", () => {
    const input = {
      code: 0,
      data_list: [
        { id: 1, nested_obj: { key_name: "a" } },
        { id: 2, nested_obj: { key_name: "b" } },
      ],
      meta: { total_count: 2, page_info: { page_size: 10 } },
    }
    const result = deepCamelize(input)
    expect(result).toEqual({
      code: 0,
      dataList: [
        { id: 1, nestedObj: { keyName: "a" } },
        { id: 2, nestedObj: { keyName: "b" } },
      ],
      meta: { totalCount: 2, pageInfo: { pageSize: 10 } },
    })
  })

  it("不修改原始输入对象", () => {
    const input = { stage_id: "3-8" }
    const inputCopy = JSON.parse(JSON.stringify(input))
    deepCamelize(input)
    expect(input).toEqual(inputCopy) // 原始对象不变
  })
})

describe("formatDateTime", () => {
  it("ISO 时间格式化为 MM-DD HH:mm:ss", () => {
    const result = formatDateTime("2026-09-27T12:34:56Z")
    expect(result).toMatch(/^\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
  })

  it("null/undefined/空字符串返回 —", () => {
    expect(formatDateTime(null)).toBe("—")
    expect(formatDateTime(undefined)).toBe("—")
    expect(formatDateTime("")).toBe("—")
  })

  it("非法日期返回 —", () => {
    expect(formatDateTime("not-a-date")).toBe("—")
  })
})

describe("formatDuration", () => {
  it("小于 1000ms 显示毫秒", () => {
    expect(formatDuration(0)).toBe("0ms")
    expect(formatDuration(830)).toBe("830ms")
    expect(formatDuration(999)).toBe("999ms")
  })

  it("1000ms-60s 显示秒（1位小数）", () => {
    expect(formatDuration(1000)).toBe("1.0s")
    expect(formatDuration(1500)).toBe("1.5s")
    expect(formatDuration(59500)).toBe("59.5s")
  })

  it("60s 以上显示分秒", () => {
    expect(formatDuration(60000)).toBe("1m0s")
    expect(formatDuration(252000)).toBe("4m12s")
  })

  it("null/undefined 返回 —", () => {
    expect(formatDuration(null)).toBe("—")
    expect(formatDuration(undefined)).toBe("—")
  })
})

describe("asPercent", () => {
  it("0..1 转百分比", () => {
    expect(asPercent(0)).toBe("0%")
    expect(asPercent(0.5)).toBe("50%")
    expect(asPercent(1)).toBe("100%")
    expect(asPercent(0.1234)).toBe("12%")
  })

  it("指定小数位数", () => {
    expect(asPercent(0.1234, 2)).toBe("12.34%")
    expect(asPercent(0.5, 1)).toBe("50.0%")
  })

  it("null/undefined 返回 —", () => {
    expect(asPercent(null)).toBe("—")
    expect(asPercent(undefined)).toBe("—")
  })
})

describe("cn", () => {
  it("合并 class 字符串", () => {
    expect(cn("a", "b")).toBe("a b")
  })

  it("过滤 falsy 值", () => {
    expect(cn("a", false, null, undefined, "b")).toBe("a b")
  })

  it("tailwind 冲突时后者覆盖前者", () => {
    expect(cn("text-red-500", "text-blue-500")).toBe("text-blue-500")
  })
})
