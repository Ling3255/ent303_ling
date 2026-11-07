import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { useI18n } from "../i18n.jsx";

export default function History() {
  const { user, openLogin } = useAuth();
  const { t, locale } = useI18n();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (user) api.myChecks().then(setRows, (e) => setError(e.message));
  }, [user]);

  if (!user)
    return (
      <div className="card">
        {t("hist.login")}
        <button className="link" onClick={openLogin}>
          {t("hist.loginBtn")}
        </button>
      </div>
    );
  if (error) return <div className="error">{error}</div>;
  return (
    <div className="card">
      <h2>{t("hist.title")}</h2>
      <p className="hint">
        {t("hist.used", { used: user.used, quota: user.quota ? ` / ${user.quota}` : "" })}
      </p>
      {!rows ? (
        t("rep.loading")
      ) : rows.length === 0 ? (
        <p className="muted">{t("hist.empty")}</p>
      ) : (
        <table className="conditions">
          <thead>
            <tr>
              <th>{t("hist.time")}</th>
              <th>{t("hist.text")}</th>
              <th>{t("hist.result")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{new Date(r.created_at).toLocaleString(locale)}</td>
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
