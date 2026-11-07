import { useState } from "react";
import { api } from "../api.js";

export default function LoginModal({ domains, onDone, onClose }) {
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
        <h2>学校邮箱登录</h2>
        <p className="hint">
          只收集邮箱，用于统计每月使用次数。{domains.length > 0 && `支持：${domains.map((d) => "@" + d).join("、")}`}
        </p>
        {stage === "email" ? (
          <form onSubmit={send}>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@student.xjtlu.edu.cn" autoFocus />
            <button className="primary" type="submit" disabled={busy || !email.includes("@")}>
              发送验证码
            </button>
          </form>
        ) : (
          <form onSubmit={verify}>
            <p className="hint">
              验证码已发送到 {email}，10 分钟内有效。
              {devCode && (
                <>
                  <br />
                  <span className="dev-code">开发模式（未配置邮件服务）验证码：{devCode}</span>
                </>
              )}
            </p>
            <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="6 位验证码" maxLength={6} autoFocus />
            <button className="primary" type="submit" disabled={busy || code.trim().length !== 6}>
              登录
            </button>
            <button type="button" className="link" onClick={() => setStage("email")}>
              换个邮箱
            </button>
          </form>
        )}
        {error && <div className="error">{error}</div>}
      </div>
    </div>
  );
}
