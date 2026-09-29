import { BrowserRouter, Navigate, Route, Routes } from "react-router"
import { Layout } from "@/components/Layout"
import Dashboard from "@/pages/Dashboard"
import Live from "@/pages/Live"
import Replay from "@/pages/Replay"
import Resources from "@/pages/Resources"
import Training from "@/pages/Training"
import RagPage from "@/pages/kb/RagPage"
import GraphPage from "@/pages/kb/GraphPage"
import OperatorPage from "@/pages/kb/OperatorPage"

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="live" element={<Live />} />
          <Route path="replay" element={<Replay />} />
          <Route path="resources" element={<Resources />} />
          <Route path="training" element={<Training />} />
          <Route path="kb">
            <Route index element={<Navigate to="rag" replace />} />
            <Route path="rag" element={<RagPage />} />
            <Route path="graph" element={<GraphPage />} />
            <Route path="operator" element={<OperatorPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
