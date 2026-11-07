import { Link, NavLink, Route, Routes } from "react-router-dom";
import NewCheck from "./pages/NewCheck.jsx";
import Report from "./pages/Report.jsx";
import PrintReport from "./pages/PrintReport.jsx";
import History from "./pages/History.jsx";
import { AuthProvider, useAuth } from "./auth.jsx";

function AccountBar() {
  const { user, openLogin, logout } = useAuth();
  if (!user)
    return (
      <button className="ghost small-btn" onClick={openLogin}>
        学校邮箱登录
      </button>
    );
  return (
    <div className="account">
      {user.quota && (
        <span className="quota" title="免费版每月次数">
          本月 {user.used}/{user.quota}
        </span>
      )}
      <span className="email" title={user.email}>
        {user.email}
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
  const { user } = useAuth();
  return (
    <Routes>
      <Route path="/checks/:id/print" element={<PrintReport />} />
      <Route
        path="*"
        element={
          <div className="app">
            <header className="topbar">
              <div className="topbar-inner">
                <Link to="/" className="brand">
                  <span className="brand-mark">✓</span>
                  <span>CiteCheck</span>
                </Link>
                <nav className="nav">
                  <NavLink to="/" end>
                    新的检查
                  </NavLink>
                  {user && <NavLink to="/history">我的记录</NavLink>}
                </nav>
                <AccountBar />
              </div>
            </header>
            <main>
              <Routes>
                <Route path="/" element={<NewCheck />} />
                <Route path="/checks/:id" element={<Report />} />
                <Route path="/history" element={<History />} />
              </Routes>
            </main>
            <footer className="footer">系统只提示差异，请核对原文 · 上传的 PDF 只用于当次检查，7 天后自动删除</footer>
          </div>
        }
      />
    </Routes>
  );
}
