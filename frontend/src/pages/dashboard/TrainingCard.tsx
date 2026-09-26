import { Link } from "react-router"
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts"
import { Card } from "@/components/Card"
import { asPercent } from "@/lib/utils"
import type { TrainingResponse } from "@/types"

export function TrainingCard({ data }: { data: TrainingResponse | null }) {
  const run = data?.runs?.[0] ?? null

  return (
    <Card
      title="训练进度"
      extra={<Link to="/training" className="text-xs text-[hsl(var(--primary))] hover:underline">详情</Link>}
    >
      {!data?.connected ? (
        <p className="mb-2 rounded-sm border border-dashed border-amber-400/50 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-300">
          V100 未接入（TODO-V100）；下图为 {run?.example ? "MOCK 示例曲线" : "占位"}，非真实训练。
        </p>
      ) : null}

      {run && run.metrics.length ? (
        <div className="h-40 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={run.metrics} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
              <CartesianGrid stroke="hsl(222 30% 20%)" strokeDasharray="3 3" />
              <XAxis dataKey="step" tick={{ fontSize: 10, fill: "#94a3b8" }} />
              <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} domain={["auto", "auto"]} />
              <Tooltip
                contentStyle={{
                  background: "hsl(222 44% 10%)",
                  border: "1px solid hsl(222 30% 20%)",
                  fontSize: 12,
                }}
              />
              <Line type="monotone" dataKey="trainLoss" name="train loss" stroke="#38bdf8" dot={false} />
              <Line type="monotone" dataKey="evalLoss" name="eval loss" stroke="#a78bfa" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="py-8 text-center text-xs text-slate-500">暂无训练数据</p>
      )}

      {run ? (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400">
          <span>底座：{run.baseModel}</span>
          <span>
            LoRA r{run.lora.rank}/α{run.lora.alpha}/p{run.lora.dropout}
          </span>
          <span>格式合规率：{asPercent(run.eval.formatCompliance)}</span>
        </div>
      ) : null}
    </Card>
  )
}
