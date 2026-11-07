import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, tokenStore } from "./api.js";
import LoginModal from "./components/LoginModal.jsx";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [config, setConfig] = useState(null); // 后端 /api/health 里的 auth 配置
  const [loginOpen, setLoginOpen] = useState(false);

  const refresh = useCallback(async () => {
    if (!tokenStore.get()) return setUser(null);
    try {
      setUser(await api.me());
    } catch {
      tokenStore.set(null);
      setUser(null);
    }
  }, []);

  useEffect(() => {
    refresh();
    api.health().then((h) => setConfig(h.auth || null)).catch(() => {});
  }, [refresh]);

  const logout = async () => {
    await api.logout().catch(() => {});
    tokenStore.set(null);
    setUser(null);
  };

  const onLoggedIn = ({ token, user: u }) => {
    tokenStore.set(token);
    setUser(u);
    setLoginOpen(false);
  };

  return (
    <AuthContext.Provider value={{ user, config, refresh, logout, openLogin: () => setLoginOpen(true) }}>
      {children}
      {loginOpen && <LoginModal domains={config?.domains || []} onDone={onLoggedIn} onClose={() => setLoginOpen(false)} />}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
