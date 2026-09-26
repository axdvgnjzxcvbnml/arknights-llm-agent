import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts"
import { fetchTraining } from "@/api/endpoints"
import { Card, EmptyState } from "@/components/Card"
import { EvidenceBadge } from "@/components/EvidenceBadge"
import { usePolling } from "@/lib/hooks"
import { asPercent } from "@/lib/utils"

export default function Training() {
  const { data } = usePolling(fetchTraining, 20000)
  if (!data) return <Card title="训练监控"><EmptyState text="加载中…" /></Card>

  return (
    <div className="space-y-4">
      {!data.connected ? (
        <p className="rounded-md border border-dashed border-amber-400/50 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          V100 未接入（TODO-V100）：当前展示的是 mock 示例曲线，非真实训练；真机 metrics 由
          /api/training/runs 读取 results/ 下 trainer 落盘文件提供。
        </p>
      ) : null}

      {data.runs.length === 0 ? (
        <Card title="训练监控"><EmptyState text="暂无训练 run" hint="V100 上启动 SFT 后在此展示 loss/eval。" /></Card>
      ) : (
        data.runs.map((run) => (
          <Card
            key={run.runId}
            title={`SFT · ${run.runId}`}
            extra={
              <span className="flex items-center gap-2">
                {run.example ? <EvidenceBadge level="mock" source="示例数据" /> : null}
                <span className="text-xs text-slate-400">{run.status}</span>
              </span>
            }
          >
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={run.metrics} margin={{ top: 8, right: 16, bottom: 0, left: -12 }}>
                  <CartesianGrid stroke="hsl(222 30% 20%)" strokeDasharray="3 3" />
                  <XAxis dataKey="step" tick={{ fontSize: 11, fill: "#94a3b8" }} />
                  <YAxis tick={{ fontSize: 11, fill: "#94a3b8" }} domain={["auto", "auto"]} />
                  <Tooltip
                    contentStyle={{ background: "hsl(222 44% 10%)", border: "1px solid hsl(222 30% 20%)" }}
                  />
                  <Line type="monotone" dataKey="trainLoss" name="train loss" stroke="#38bdf8" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="evalLoss" name="eval loss" stroke="#a78bfa" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-400">
              <span>底座：{run.baseModel}</span>
              <span>LoRA rank={run.lora.rank} alpha={run.lora.alpha} dropout={run.lora.dropout}</span>
              <span>格式合规率：{asPercent(run.eval.formatCompliance)}</span>
              <span>准确率：{asPercent(run.eval.accuracy)}</span>
            </div>
          </Card>
        ))
      )}
    </div>
  )
}
