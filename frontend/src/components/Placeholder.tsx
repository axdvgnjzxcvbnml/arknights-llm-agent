import { Card, EmptyState } from "./Card"

/** 等待 Qwen web/ 或 web-kb 页面并入的占位页。 */
export function PlaceholderPage({
  title,
  from,
  route,
}: {
  title: string
  from: string
  route: string
}) {
  return (
    <Card title={title}>
      <EmptyState
        text={`该页面将由 ${from} 提供（${route}）`}
        hint="等对应前端到位后按 docs/dashboard_design.md 并入统一外壳，本占位不实现其逻辑。"
      />
    </Card>
  )
}
