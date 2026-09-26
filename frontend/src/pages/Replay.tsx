import { PlaceholderPage } from "@/components/Placeholder"

export default function Replay() {
  return (
    <PlaceholderPage
      title="对局回放（/replay）"
      from="Qwen web/"
      route="/replay、/replay/:episodeId → /api/episodes、/api/episode/{id}/steps"
    />
  )
}
