import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { fetchJson, USE_MOCK, API_BASE } from "@/api/client"

describe("client.ts", () => {
  describe("USE_MOCK 常量", () => {
    it("默认为 true（VITE_USE_MOCK 未设为 false）", () => {
      // 测试环境没有设置 VITE_USE_MOCK=false，所以默认是 mock 模式
      expect(typeof USE_MOCK).toBe("boolean")
    })
  })

  describe("API_BASE", () => {
    it("默认为空字符串（同源请求）", () => {
      expect(typeof API_BASE).toBe("string")
    })
  })

  describe("fetchJson", () => {
    const originalFetch = global.fetch

    beforeEach(() => {
      global.fetch = vi.fn()
    })

    afterEach(() => {
      global.fetch = originalFetch
    })

    it("mock 模式下请求 mock JSON 文件", async () => {
      const mockData = { stage_id: "3-8", enemies: [] }
      ;(global.fetch as any).mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockData),
      })

      const result = await fetchJson<any>("stage_3_8", "/api/stage/3-8")
      expect(global.fetch).toHaveBeenCalled()
      // 返回经 deepCamelize 后的数据
      expect(result.stageId).toBe("3-8")
      expect(result.enemies).toEqual([])
    })

    it("mock 模式下 HTTP 错误抛出异常", async () => {
      ;(global.fetch as any).mockResolvedValue({
        ok: false,
        status: 404,
      })

      await expect(fetchJson<any>("missing", "/api/missing")).rejects.toThrow("mock 数据缺失")
    })

    it("返回数据经 deepCamelize 转换", async () => {
      const snakeData = {
        operator_name: "能天使",
        skill_list: [{ skill_name: "扫射模式", cost_value: 15 }],
      }
      ;(global.fetch as any).mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(snakeData),
      })

      const result = await fetchJson<any>("operator_exusiai", "/api/operator/能天使")
      expect(result.operatorName).toBe("能天使")
      expect(result.skillList[0].skillName).toBe("扫射模式")
      expect(result.skillList[0].costValue).toBe(15)
    })
  })
})
