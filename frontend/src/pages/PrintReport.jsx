import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api.js";
import { COLOR_TEXT, SEVERITY_TEXT } from "../labels.js";

// 一页证据单：用浏览器“打印 → 存储为 PDF”导出，中文字体不会丢
export default function PrintReport() {
  const { id } = useParams();
  const [check, setCheck] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.check(id).then(setCheck, (e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    if (check?.report) {
      document.title = `CiteCheck 证据单 ${new Date(check.created_at).toLocaleDateString("zh-CN")}`;
      const t = setTimeout(() => window.print(), 400);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [check]);

  if (error) return <div className="error">{error}</div>;
  if (!check?.report) return <div className="print-page">加载中…</div>;
  const { report } = check;
  const papers = Object.fromEntries(report.papers.map((p, i) => [p.id, { ...p, n: i + 1 }]));
  const rows = report.sentences.filter((s) => s.selected && s.color !== "gray");

  return (
    <div className="print-page">
      <div className="print-actions no-print">
        <button className="primary" onClick={() => window.print()}>
          打印 / 存为 PDF
        </button>
        <span className="hint">在打印对话框中选择“存储为 PDF”。</span>
      </div>
      <header className="print-head">
        <h1>CiteCheck 证据单</h1>
        <div>
          检查时间 {new Date(check.created_at).toLocaleString("zh-CN")} · 共 {rows.length} 句 · 红 {report.summary.red} / 黄{" "}
          {report.summary.yellow} / 绿 {report.summary.green}
        </div>
      </header>

      <section>
        <h2>所引论文</h2>
        <ol className="print-papers">
          {report.papers.map((p) => (
            <li key={p.id}>
              {p.title}（{(p.authors || []).slice(0, 2).join(", ")}
              {p.authors?.length > 2 ? " 等" : ""}，{p.year || "年份未知"}）— 来源：{p.source.label}
              {p.venue ? `，${p.venue}` : ""}
            </li>
          ))}
        </ol>
      </section>

      <table className="print-table">
        <thead>
          <tr>
            <th style={{ width: "28%" }}>句子</th>
            <th style={{ width: "9%" }}>结果</th>
            <th style={{ width: "14%" }}>② 支持</th>
            <th>③ 可比 · 原文出处</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.idx}>
              <td>{s.text}</td>
              <td>
                <span className={`print-dot ${s.color}`} />
                {COLOR_TEXT[s.color]}
              </td>
              <td>{s.support.results.map((r) => `${r.subject ? r.subject + "：" : ""}${r.label}`).join("；")}</td>
              <td>
                {s.comparability.level !== "na" && (
                  <div>
                    <strong>{s.comparability.label}</strong>
                    {s.comparability.pairs
                      .flatMap((p) => p.fields.filter((f) => f.severity === "major" || f.severity === "minor"))
                      .map((f) => (
                        <div key={f.field + f.a + f.b}>
                          {f.label}：{f.a || "未写明"} vs {f.b || "未写明"}（{SEVERITY_TEXT[f.severity]}）
                        </div>
                      ))}
                  </div>
                )}
                {s.support.results.flatMap((r) =>
                  r.evidence.slice(0, 1).map((ev) => (
                    <div key={r.claim_id + ev.paragraph_id} className="print-quote">
                      [{papers[r.paper_id]?.n}] p.{ev.page ?? "?"}：“{ev.quote.length > 140 ? ev.quote.slice(0, 140) + "…" : ev.quote}”
                    </div>
                  )),
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <footer className="print-foot">{report.disclaimer}</footer>
    </div>
  );
}
