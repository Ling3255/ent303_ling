import { Link, Route, Routes } from "react-router-dom";
import NewCheck from "./pages/NewCheck.jsx";
import Report from "./pages/Report.jsx";
import PrintReport from "./pages/PrintReport.jsx";
import History from "./pages/History.jsx";
import { AuthProvider, useAuth } from "./auth.jsx";

function AccountBar() {
  const { user, openLogin, logout } = useAuth();
  if (!user)
    return (
      <div className="account">
        <button onClick={openLogin}>学校邮箱登录</button>
      </div>
    );
  return (
    <div className="account">
      <Link to="/history">我的记录</Link>
      <span className="muted">
        {user.email} · 本月 {user.used}
        {user.quota ? `/${user.quota}` : ""} 次
      </span>
      <button className="link" onClick={logout}>
        退出
      </button>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  );
}

function AppRoutes() {
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
              <AccountBar />
            </header>
            <main>
              <Routes>
                <Route path="/" element={<NewCheck />} />
                <Route path="/checks/:id" element={<Report />} />
                <Route path="/history" element={<History />} />
              </Routes>
            </main>
            <footer className="footer">系统只提示差异，请核对原文。上传的 PDF 只用于当次检查，7 天后自动删除。</footer>
          </div>
        }
      />
    </Routes>
  );
}
