import { Routes, Route, Navigate } from 'react-router';
import Layout from './components/Layout';
import RagPage from './pages/RagPage';
import GraphPage from './pages/GraphPage';
import OperatorPage from './pages/OperatorPage';

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/rag" replace />} />
        <Route path="/rag" element={<RagPage />} />
        <Route path="/graph" element={<GraphPage />} />
        <Route path="/operator" element={<OperatorPage />} />
        <Route path="*" element={<Navigate to="/rag" replace />} />
      </Routes>
    </Layout>
  );
}
