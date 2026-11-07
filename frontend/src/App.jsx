import { useEffect } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import NewCheck from "./pages/NewCheck.jsx";
import Report from "./pages/Report.jsx";
import PrintReport from "./pages/PrintReport.jsx";
import History from "./pages/History.jsx";
import { AuthProvider, useAuth } from "./auth.jsx";
import { LangToggle, useI18n } from "./i18n.jsx";

function AccountBar() {
  const { user, openLogin, logout } = useAuth();
  const { t } = useI18n();
  if (!user)
    return (
      <button className="ghost small-btn" onClick={openLogin} title={t("nav.login")}>
        <span className="label-long">{t("nav.login")}</span>
        <span className="label-short">{t("nav.loginShort")}</span>
      </button>
    );
  return (
    <div className="account">
      {user.quota && (
        <span className="quota" title={t("nav.quotaTitle")}>
          {t("nav.quota", { used: user.used, quota: user.quota })}
        </span>
      )}
      <span className="email" title={user.email}>
        {user.email}
      </span>
      <button className="link" onClick={logout}>
        {t("nav.logout")}
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
  const { t, lang } = useI18n();
  const { pathname } = useLocation();
  // 证据单页自己设置标题（导出 PDF 的文件名），其他页面用应用标题
  useEffect(() => {
    if (!pathname.endsWith("/print")) document.title = t("app.title");
  }, [pathname, lang, t]);
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
                    {t("nav.new")}
                  </NavLink>
                  {user && <NavLink to="/history">{t("nav.history")}</NavLink>}
                </nav>
                <div className="topbar-right">
                  <LangToggle />
                  <AccountBar />
                </div>
              </div>
            </header>
            <main>
              <Routes>
                <Route path="/" element={<NewCheck />} />
                <Route path="/checks/:id" element={<Report />} />
                <Route path="/history" element={<History />} />
              </Routes>
            </main>
            <footer className="footer">{t("footer")}</footer>
          </div>
        }
      />
    </Routes>
  );
}
