import { useState } from "react";
import { api } from "../api.js";
import { SEVERITY_COLOR, fieldLabel, keyFindings, levelLabel, markerName, markerSide, sourceLabel, verdictLabel } from "../labels.js";
import { useI18n } from "../i18n.jsx";

const SUPPORT_COLOR = { supported: "green", not_found: "yellow", contradicted: "red", number_mismatch: "red" };
const SOURCE_COLOR = { published: "green", preprint: "yellow", unknown: "yellow", not_found: "red" };
const SEVERITY_RANK = { major: 0, minor: 1, unknown: 2, same: 3 };

export default function SentenceDetail({ number, checkId, sentence, papersById, onOpenPdf }) {
  const { t, tx } = useI18n();
  if (sentence.color === "gray") {
    return (
      <div className="card">
        <SentenceHeader number={number} sentence={sentence} />
        <p className="muted">{tx(sentence.note)}</p>
      </div>
    );
  }
  const { source, support, comparability } = sentence;
  const findings = keyFindings(sentence, t, tx);
  const paperTitle = (pid) => papersById[pid]?.title || t("det.paper");
  const layers = [
    { key: "source", color: source.color, label: source.items.map((i) => sourceLabel(i, t, tx)).join(" / ") },
    { key: "support", color: support.color, label: verdictLabel({ label: support.label, verdict: support.level }, t, tx) },
    { key: "comparability", color: comparability.color, label: levelLabel(comparability, t, tx) },
  ];

  return (
    <div className="detail">
      <div className={`card verdict-card ${sentence.color}`}>
        <SentenceHeader number={number} sentence={sentence} />
        <div className="layer-pills">
          {layers.map((l) => (
            <a key={l.key} href={`#layer-${l.key}`} className={`layer-pill ${l.color || "neutral"}`}>
              <span>{t(`layer.${l.key}`)}</span>
              <strong>{l.label}</strong>
            </a>
          ))}
        </div>
        {findings.length > 0 ? (
          <ul className="findings">
            {findings.slice(0, 4).map((f, i) => (
              <li key={i} className={f.color}>
                <span className="finding-layer">{f.layer}</span>
                <div>
                  <div className="finding-text">{f.text}</div>
                  {f.reason && <div className="finding-reason">{f.reason}</div>}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="all-good">{t("det.allGood")}</p>
        )}
      </div>

      <Layer name="source" color={source.color} summary={layers[0].label} checkId={checkId} sentence={sentence}>
        <ul className="plain">
          {source.items.map((item) => {
            const p = papersById[item.paper_id];
            return (
              <li key={item.paper_id} className="source-row">
                <span className={`tag ${SOURCE_COLOR[item.status]}`}>{sourceLabel(item, t, tx)}</span>
                <div>
                  <div>{item.title || t("det.untitled")}</div>
                  <div className="muted small">
                    {[
                      p?.authors?.[0] && `${p.authors[0]}${p.authors.length > 1 ? t("det.etal") : ""}`,
                      p?.year,
                      item.status === "published" && p?.venue,
                      item.status === "preprint" && t("det.preprint"),
                      item.status === "unknown" && t("det.lookupFailed"),
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </Layer>

      <Layer name="support" color={support.color} summary={layers[1].label} checkId={checkId} sentence={sentence}>
        {support.results.map((r) => (
          <div key={r.claim_id} className="claim">
            <div className="claim-head">
              <span className={`tag ${SUPPORT_COLOR[r.verdict]}`}>{verdictLabel(r, t, tx)}</span>
              <strong>{r.subject || t("det.claim")}</strong>
              {r.values?.length > 0 && (
                <span className="num-compare">
                  {t("det.textNum")} <b>{r.values.join(", ")}</b>
                  {r.paper_value && (
                    <>
                      {" "}
                      · {t("det.paperNum")} <b className={r.verdict === "number_mismatch" ? "bad" : ""}>{r.paper_value}</b>
                    </>
                  )}
                </span>
              )}
            </div>
            {r.statement !== sentence.text && <div className="muted small">{r.statement}</div>}
            {tx(r.explanation) && <p className="explain">{tx(r.explanation)}</p>}
            {r.notes?.map((n, i) => (
              <p key={i} className="note">
                {tx(n)}
              </p>
            ))}
            {r.evidence.map((ev) => (
              <Evidence
                key={ev.paragraph_id + ev.quote}
                ev={ev}
                paperId={r.paper_id}
                paperTitle={paperTitle(r.paper_id)}
                onOpenPdf={onOpenPdf}
              />
            ))}
            {!r.evidence.length && r.candidates?.length > 0 && r.paper_id && (
              <div className="muted small">
                {t("det.candidates", {
                  pages: [...new Set(r.candidates.map((c) => c.page).filter(Boolean))].slice(0, 5).join(", "),
                })}
                <button className="link" onClick={() => onOpenPdf({ paperId: r.paper_id, page: r.candidates[0].page || 1, boxes: [] })}>
                  {t("det.openPdfSelf")}
                </button>
              </div>
            )}
          </div>
        ))}
      </Layer>

      <Layer
        name="comparability"
        color={comparability.color}
        summary={layers[2].label}
        checkId={checkId}
        sentence={sentence}
        core
      >
        {comparability.level === "na" ? (
          <p className="muted">{t("det.noComparison")}</p>
        ) : (
          comparability.pairs.map((pair, i) => <ConditionTable key={i} pair={pair} onOpenPdf={onOpenPdf} papersById={papersById} />)
        )}
        {comparability.level === "consistent" && <p className="note">{t("det.consistent")}</p>}
      </Layer>
    </div>
  );
}

function SentenceHeader({ number, sentence }) {
  const { t } = useI18n();
  return (
    <div className="sentence-head">
      <span className={`num big ${sentence.color}`}>{number}</span>
      <div className="sentence-main">
        <span className={`tag ${sentence.color}`}>{t(`color.${sentence.color}`)}</span>
        <blockquote className="quoted">{sentence.text}</blockquote>
      </div>
    </div>
  );
}

function Layer({ name, color, summary, children, checkId, sentence, core }) {
  const { t } = useI18n();
  // 绿色的层默认收起，有问题的层展开
  const [open, setOpen] = useState(color !== "green");
  return (
    <section id={`layer-${name}`} className={`card layer ${color || "neutral"}`}>
      <header onClick={() => setOpen(!open)}>
        <h3>{t(`layer.${name}`)}</h3>
        {core && <span className="core-badge">{t("home.core")}</span>}
        <span className={`tag ${color || "neutral"}`}>{summary}</span>
        <span className="chev">{open ? t("det.collapse") : t("det.expand")}</span>
      </header>
      {open && (
        <div className="layer-body">
          {children}
          <Disagree checkId={checkId} sentence={sentence} layer={name} label={summary} />
        </div>
      )}
    </section>
  );
}

function Evidence({ ev, paperId, paperTitle, onOpenPdf }) {
  const { t } = useI18n();
  const [context, setContext] = useState(false);
  return (
    <div className="evidence">
      <div className="evidence-meta">
        <span className="page-badge">p.{ev.page ?? "?"}</span>
        <span className="evidence-src">
          {paperTitle}
          {ev.section ? ` · ${ev.section}` : ""}
          {ev.kind === "table" && t("det.table")}
        </span>
        <button className="link" onClick={() => onOpenPdf({ paperId, page: ev.page || 1, boxes: ev.boxes, quote: ev.quote })}>
          {t("det.viewSource")}
        </button>
      </div>
      <blockquote className="evidence-quote">{ev.quote}</blockquote>
      {ev.text && ev.text.length > ev.quote.length + 20 && (
        <>
          <button className="link small" onClick={() => setContext(!context)}>
            {context ? t("det.hideContext") : t("det.showContext")}
          </button>
          {context && <Highlighted text={ev.text} quote={ev.quote} />}
        </>
      )}
    </div>
  );
}

function Highlighted({ text, quote }) {
  const s = text || "";
  const idx = quote ? s.toLowerCase().indexOf(quote.toLowerCase()) : -1;
  if (idx < 0) return <div className="para">{s}</div>;
  return (
    <div className="para">
      {s.slice(0, idx)}
      <mark>{s.slice(idx, idx + quote.length)}</mark>
      {s.slice(idx + quote.length)}
    </div>
  );
}

function ConditionTable({ pair, onOpenPdf, papersById }) {
  const { t, tx } = useI18n();
  const fields = [...pair.fields].sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]);
  const differing = fields.filter((f) => f.severity !== "same");
  const same = fields.filter((f) => f.severity === "same");
  const markers = fields.flatMap((f) => f.markers.map((m) => ({ ...m, severity: f.severity })));
  const nameA = pair.a.subject || t("det.resultA");
  const nameB = pair.b.subject || t("det.resultB");

  return (
    <div className="pair">
      <div className="pair-title">
        <strong>{nameA}</strong> <span className="vs">vs</span> <strong>{nameB}</strong>
      </div>

      {markers.map((m, i) => (
        <div key={i} className={`callout ${SEVERITY_COLOR[m.severity]}`}>
          <div className="callout-title">{t("det.keyDiff", { name: markerName(m, t, tx) })}</div>
          <div className="callout-vs">
            <span>
              {nameA}: <b>{markerSide(m.a, t, tx)}</b>
            </span>
            <span>
              {nameB}: <b>{markerSide(m.b, t, tx)}</b>
            </span>
          </div>
          <div className="callout-reason">{tx(m.reason)}</div>
        </div>
      ))}

      {differing.length > 0 && (
        <div className="table-wrap">
          <table className="conditions">
            <thead>
              <tr>
                <th>{t("det.condition")}</th>
                <th>{nameA}</th>
                <th>{nameB}</th>
                <th>{t("det.verdict")}</th>
              </tr>
            </thead>
            <tbody>
              {differing.map((f) => (
                <tr key={f.field} className={SEVERITY_COLOR[f.severity]}>
                  <td className="cond-name">{fieldLabel(f, t, tx)}</td>
                  <td>
                    <Cond value={f.a} quote={f.a_quote} page={f.a_page} paperId={pair.a.paper_id} onOpenPdf={onOpenPdf} />
                  </td>
                  <td>
                    <Cond value={f.b} quote={f.b_quote} page={f.b_page} paperId={pair.b.paper_id} onOpenPdf={onOpenPdf} />
                  </td>
                  <td>
                    <span className={`tag ${SEVERITY_COLOR[f.severity]}`}>{t(`sev.${f.severity}`)}</span>
                    {!f.markers.length && <div className="small muted reason">{tx(f.reason)}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {same.length > 0 && (
        <div className="same-row">
          <span className="tag green">{t("det.same")}</span>
          {same.map((f) => (
            <span key={f.field} className="same-item">
              {fieldLabel(f, t, tx)} <b>{f.a}</b>
            </span>
          ))}
        </div>
      )}

      <div className="small muted">
        {[pair.a, pair.b]
          .filter((x) => x.paper_id)
          .map((x) => t("det.from", { who: x.subject || t("det.result"), title: papersById[x.paper_id]?.title || t("det.paper") }))
          .filter((v, i, arr) => arr.indexOf(v) === i)
          .join("; ")}
      </div>
    </div>
  );
}

function Cond({ value, quote, page, paperId, onOpenPdf }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  if (!value) return <span className="muted">{t("det.notStated")}</span>;
  return (
    <div className="cond">
      <strong>{value}</strong>
      {(quote || page) && (
        <div className="cond-actions">
          {quote && (
            <button className="link small" onClick={() => setOpen(!open)}>
              {open ? t("det.hideQuote") : t("det.quote")}
            </button>
          )}
          {page && paperId && (
            <button className="link small" onClick={() => onOpenPdf({ paperId, page, boxes: [], quote })}>
              p.{page} →
            </button>
          )}
        </div>
      )}
      {open && quote && <div className="quote-small">“{quote}”</div>}
    </div>
  );
}

function Disagree({ checkId, sentence, layer, label }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [state, setState] = useState("idle");
  if (state === "sent") return <div className="small muted feedback-row">{t("fb.thanks")}</div>;
  if (!open)
    return (
      <div className="feedback-row">
        <button className="link small muted-link" onClick={() => setOpen(true)}>
          {t("fb.open")}
        </button>
      </div>
    );
  return (
    <form
      className="disagree"
      onSubmit={async (e) => {
        e.preventDefault();
        setState("sending");
        try {
          await api.feedback(checkId, { sentence_idx: sentence.idx, layer, system_label: label, reason });
          setState("sent");
        } catch {
          setState("error");
        }
      }}
    >
      <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t("fb.placeholder")} rows={2} autoFocus />
      <div className="disagree-actions">
        <button type="submit" className="small-btn" disabled={reason.trim().length < 2 || state === "sending"}>
          {t("fb.submit")}
        </button>
        <button type="button" className="link" onClick={() => setOpen(false)}>
          {t("fb.cancel")}
        </button>
        {state === "error" && <span className="error-inline">{t("fb.error")}</span>}
      </div>
    </form>
  );
}
