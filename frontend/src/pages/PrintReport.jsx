import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api.js";
import { LangToggle, useI18n } from "../i18n.jsx";
import { fieldLabel, levelLabel, markerSide, sourceLabel, verdictLabel } from "../labels.js";

// 一页证据单：用浏览器“打印 → 存储为 PDF”导出，中文字体不会丢
export default function PrintReport() {
  const { id } = useParams();
  const { t, tx, locale } = useI18n();
  const [check, setCheck] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.check(id).then(setCheck, (e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    if (check?.report) {
      const timer = setTimeout(() => window.print(), 400);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [check]);

  useEffect(() => {
    if (check?.report) document.title = t("print.docTitle", { date: new Date(check.created_at).toLocaleDateString(locale) });
  }, [check, t, locale]);

  if (error) return <div className="error">{error}</div>;
  if (!check?.report) return <div className="print-page">{t("print.loading")}</div>;
  const { report } = check;
  const papers = Object.fromEntries(report.papers.map((p, i) => [p.id, { ...p, n: i + 1 }]));
  const rows = report.sentences.filter((s) => s.selected && s.color !== "gray");

  return (
    <div className="print-page">
      <div className="print-actions no-print">
        <button className="primary" onClick={() => window.print()}>
          {t("print.button")}
        </button>
        <span className="hint">{t("print.hint")}</span>
        <span style={{ marginLeft: "auto" }}>
          <LangToggle />
        </span>
      </div>
      <header className="print-head">
        <h1>{t("print.title")}</h1>
        <div>
          {t("print.meta", {
            time: new Date(check.created_at).toLocaleString(locale),
            n: rows.length,
            r: report.summary.red,
            y: report.summary.yellow,
            g: report.summary.green,
          })}
        </div>
      </header>

      <section>
        <h2>{t("print.papers")}</h2>
        <ol className="print-papers">
          {report.papers.map((p) => (
            <li key={p.id}>
              {t("print.paperLine", {
                title: p.title,
                authors:
                  (p.authors || []).slice(0, 2).join(", ") + ((p.authors?.length || 0) > 2 ? t("det.etal") : ""),
                year: p.year || t("home.yearUnknown"),
                source: sourceLabel(p.source, t, tx),
              })}
              {p.venue ? `, ${p.venue}` : ""}
            </li>
          ))}
        </ol>
      </section>

      <table className="print-table">
        <thead>
          <tr>
            <th style={{ width: "28%" }}>{t("print.sentence")}</th>
            <th style={{ width: "10%" }}>{t("print.result")}</th>
            <th style={{ width: "15%" }}>{t("print.support")}</th>
            <th>{t("print.comp")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.idx}>
              <td>{s.text}</td>
              <td>
                <span className={`print-dot ${s.color}`} />
                {t(`color.${s.color}`)}
              </td>
              <td>{s.support.results.map((r) => `${r.subject ? r.subject + ": " : ""}${verdictLabel(r, t, tx)}`).join("; ")}</td>
              <td>
                {s.comparability.level !== "na" && (
                  <div>
                    <strong>{levelLabel(s.comparability, t, tx)}</strong>
                    {s.comparability.pairs
                      .flatMap((p) => p.fields.filter((f) => f.severity === "major" || f.severity === "minor"))
                      .map((f) => (
                        <div key={f.field}>
                          {fieldLabel(f, t, tx)}: {f.markers?.[0] ? `${markerSide(f.markers[0].a, t, tx)} vs ${markerSide(f.markers[0].b, t, tx)}` : `${f.a || t("find.notStated")} vs ${f.b || t("find.notStated")}`}{" "}
                          ({t(`sev.${f.severity}`)})
                        </div>
                      ))}
                  </div>
                )}
                {s.support.results.flatMap((r) =>
                  r.evidence.slice(0, 1).map((ev) => (
                    <div key={r.claim_id + ev.paragraph_id} className="print-quote">
                      [{papers[r.paper_id]?.n}] p.{ev.page ?? "?"}: “{ev.quote.length > 140 ? ev.quote.slice(0, 140) + "…" : ev.quote}”
                    </div>
                  )),
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <footer className="print-foot">{tx(report.disclaimer)}</footer>
    </div>
  );
}
