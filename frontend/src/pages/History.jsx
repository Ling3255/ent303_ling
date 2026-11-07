import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";

export default function History() {
  const { user, openLogin } = useAuth();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (user) api.myChecks().then(setRows, (e) => setError(e.message));
  }, [user]);

  if (!user)
    return (
      <div className="card">
        登录后可以查看自己的检查记录。<button className="link" onClick={openLogin}>登录</button>
      </div>
    );
  if (error) return <div className="error">{error}</div>;
  return (
    <div className="card">
      <h2>我的检查记录</h2>
      <p className="hint">
        本月已用 {user.used}
        {user.quota ? ` / ${user.quota}` : ""} 次。
      </p>
      {!rows ? (
        "加载中…"
      ) : rows.length === 0 ? (
        <p className="muted">还没有检查记录。</p>
      ) : (
        <table className="conditions">
          <thead>
            <tr>
              <th>时间</th>
              <th>文字</th>
              <th>结果</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{new Date(r.created_at).toLocaleString("zh-CN")}</td>
                <td>
                  <Link to={`/checks/${r.id}`}>{r.preview}…</Link>
                </td>
                <td>
                  {r.summary ? (
                    <>
                      <span className="dot red" /> {r.summary.red} <span className="dot yellow" /> {r.summary.yellow}{" "}
                      <span className="dot green" /> {r.summary.green}
                    </>
                  ) : (
                    r.status
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
