import { PlaceholderPage } from "@/components/Placeholder"

export function KbRag() {
  return <PlaceholderPage title="RAG 检索（/kb/rag）" from="web-kb / RagPage" route="/api/search?q=&k=&doc_type=" />
}

export function KbGraph() {
  return (
    <PlaceholderPage
      title="知识图谱（/kb/graph）"
      from="web-kb / GraphPage"
      route="/api/graph/overview、/graph/node/{id}、/graph/subgraph/{stage_id}"
    />
  )
}

export function KbOperator() {
  return (
    <PlaceholderPage
      title="干员详情（/kb/operator）"
      from="web-kb / OperatorPage"
      route="/api/operator/{name}、/api/skill/{operator}/{skill_name}"
    />
  )
}
