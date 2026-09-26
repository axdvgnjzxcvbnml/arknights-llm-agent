import { BrowserRouter, Navigate, Route, Routes } from "react-router"
import { Layout } from "@/components/Layout"
import Dashboard from "@/pages/Dashboard"
import Live from "@/pages/Live"
import Replay from "@/pages/Replay"
import Resources from "@/pages/Resources"
import Training from "@/pages/Training"
import { KbGraph, KbOperator, KbRag } from "@/pages/Kb"

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
            <Route path="rag" element={<KbRag />} />
            <Route path="graph" element={<KbGraph />} />
            <Route path="operator" element={<KbOperator />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
