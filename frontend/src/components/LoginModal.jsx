import { useState } from "react";
import { api } from "../api.js";
import { useI18n } from "../i18n.jsx";

export default function LoginModal({ domains, onDone, onClose }) {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [stage, setStage] = useState("email");
  const [devCode, setDevCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function send(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api.requestCode(email);
      setDevCode(r.dev_code || "");
      setStage("code");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function verify(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onDone(await api.verify(email, code));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal login" onClick={(e) => e.stopPropagation()}>
        <h2>{t("login.title")}</h2>
        <p className="hint">
          {t("login.hint")} {domains.length > 0 && t("login.domains", { d: domains.map((d) => "@" + d).join(", ") })}
        </p>
        {stage === "email" ? (
          <form onSubmit={send}>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@student.xjtlu.edu.cn" autoFocus />
            <button className="primary" type="submit" disabled={busy || !email.includes("@")}>
              {t("login.send")}
            </button>
          </form>
        ) : (
          <form onSubmit={verify}>
            <p className="hint">
              {t("login.sent", { email })}
              {devCode && (
                <>
                  <br />
                  <span className="dev-code">{t("login.dev", { code: devCode })}</span>
                </>
              )}
            </p>
            <input value={code} onChange={(e) => setCode(e.target.value)} placeholder={t("login.code")} maxLength={6} autoFocus />
            <button className="primary" type="submit" disabled={busy || code.trim().length !== 6}>
              {t("login.submit")}
            </button>
            <button type="button" className="link" onClick={() => setStage("email")}>
              {t("login.change")}
            </button>
          </form>
        )}
        {error && <div className="error">{error}</div>}
      </div>
    </div>
  );
}
