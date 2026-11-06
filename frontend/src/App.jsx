import { Link, Route, Routes } from "react-router-dom";
import NewCheck from "./pages/NewCheck.jsx";
import Report from "./pages/Report.jsx";
import PrintReport from "./pages/PrintReport.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/checks/:id/print" element={<PrintReport />} />
      <Route
        path="*"
        element={
          <div className="app">
            <header className="topbar">
              <Link to="/" className="brand">
                <span className="brand-mark">✓</span> CiteCheck
              </Link>
              <span className="tagline">逐句核对：这段话和所引论文对得上吗？比较的结果是同条件测的吗？</span>
            </header>
            <main>
              <Routes>
                <Route path="/" element={<NewCheck />} />
                <Route path="/checks/:id" element={<Report />} />
              </Routes>
            </main>
            <footer className="footer">系统只提示差异，请核对原文。上传的 PDF 只用于当次检查，7 天后自动删除。</footer>
          </div>
        }
      />
    </Routes>
  );
}
