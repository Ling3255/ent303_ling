import { useState } from "react";
import { api } from "../api.js";
import { COLOR_TEXT, LAYER_NAMES, SEVERITY_COLOR, SEVERITY_TEXT, keyFindings } from "../labels.js";

const SUPPORT_COLOR = { supported: "green", not_found: "yellow", contradicted: "red", number_mismatch: "red" };
const SOURCE_COLOR = { published: "green", preprint: "yellow", unknown: "yellow", not_found: "red" };
const SEVERITY_RANK = { major: 0, minor: 1, unknown: 2, same: 3 };

export default function SentenceDetail({ number, checkId, sentence, papersById, onOpenPdf }) {
  if (sentence.color === "gray") {
    return (
      <div className="card">
        <SentenceHeader number={number} sentence={sentence} />
        <p className="muted">{sentence.note}</p>
      </div>
    );
  }
  const { source, support, comparability } = sentence;
  const findings = keyFindings(sentence);
  const paperTitle = (pid) => papersById[pid]?.title || "论文";
  const layers = [
    { key: "source", color: source.color, label: source.items.map((i) => i.label).join(" / ") },
    { key: "support", color: support.color, label: support.label },
    { key: "comparability", color: comparability.color, label: comparability.label },
  ];

  return (
    <div className="detail">
      <div className={`card verdict-card ${sentence.color}`}>
        <SentenceHeader number={number} sentence={sentence} />
        <div className="layer-pills">
          {layers.map((l) => (
            <a key={l.key} href={`#layer-${l.key}`} className={`layer-pill ${l.color || "neutral"}`}>
              <span>{LAYER_NAMES[l.key]}</span>
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
          <p className="all-good">三层都没有发现问题。这不代表结论一定正确，引用前请再看一眼原文。</p>
        )}
      </div>

      <Layer
        name="source"
        color={source.color}
        summary={layers[0].label}
        checkId={checkId}
        sentence={sentence}
      >
        <ul className="plain">
          {source.items.map((item) => {
            const p = papersById[item.paper_id];
            return (
              <li key={item.paper_id} className="source-row">
                <span className={`tag ${SOURCE_COLOR[item.status]}`}>{item.label}</span>
                <div>
                  <div>{item.title || "未识别标题"}</div>
                  <div className="muted small">
                    {[
                      p?.authors?.[0] && `${p.authors[0]}${p.authors.length > 1 ? " 等" : ""}`,
                      p?.year,
                      item.status === "published" && p?.venue,
                      item.status === "preprint" && "只找到预印本，未查到正式发表版本",
                      item.status === "unknown" && "学术数据接口查询失败，请稍后重试",
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

      <Layer name="support" color={support.color} summary={support.label} checkId={checkId} sentence={sentence}>
        {support.results.map((r) => (
          <div key={r.claim_id} className="claim">
            <div className="claim-head">
              <span className={`tag ${SUPPORT_COLOR[r.verdict]}`}>{r.label}</span>
              <strong>{r.subject || "论断"}</strong>
              {r.values?.length > 0 && (
                <span className="num-compare">
                  文字 <b>{r.values.join("、")}</b>
                  {r.paper_value && (
                    <>
                      {" "}
                      · 原文 <b className={r.verdict === "number_mismatch" ? "bad" : ""}>{r.paper_value}</b>
                    </>
                  )}
                </span>
              )}
            </div>
            {r.statement !== sentence.text && <div className="muted small">{r.statement}</div>}
            {r.explanation && <p className="explain">{r.explanation}</p>}
            {r.notes?.map((n) => (
              <p key={n} className="note">
                {n}
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
                检索到的候选段落在第 {[...new Set(r.candidates.map((c) => c.page).filter(Boolean))].slice(0, 5).join("、")} 页，
                <button className="link" onClick={() => onOpenPdf({ paperId: r.paper_id, page: r.candidates[0].page || 1, boxes: [] })}>
                  打开 PDF 自行核对
                </button>
              </div>
            )}
          </div>
        ))}
      </Layer>

      <Layer
        name="comparability"
        color={comparability.color}
        summary={comparability.label}
        checkId={checkId}
        sentence={sentence}
        core
      >
        {comparability.level === "na" ? (
          <p className="muted">这句话没有把两个结果放在一起比较，不做可比检查。</p>
        ) : (
          comparability.pairs.map((pair, i) => <ConditionTable key={i} pair={pair} onOpenPdf={onOpenPdf} papersById={papersById} />)
        )}
        {comparability.level === "consistent" && (
          <p className="note">未发现条件差异。这不代表两个结果一定可以直接比较，请核对原文。</p>
        )}
      </Layer>
    </div>
  );
}

function SentenceHeader({ number, sentence }) {
  return (
    <div className="sentence-head">
      <span className={`num big ${sentence.color}`}>{number}</span>
      <div className="sentence-main">
        <span className={`tag ${sentence.color}`}>{COLOR_TEXT[sentence.color]}</span>
        <blockquote className="quoted">{sentence.text}</blockquote>
      </div>
    </div>
  );
}

function Layer({ name, color, summary, children, checkId, sentence, core }) {
  // 绿色的层默认收起，有问题的层展开
  const [open, setOpen] = useState(color !== "green");
  return (
    <section id={`layer-${name}`} className={`card layer ${color || "neutral"}`}>
      <header onClick={() => setOpen(!open)}>
        <h3>{LAYER_NAMES[name]}</h3>
        {core && <span className="core-badge">核心</span>}
        <span className={`tag ${color || "neutral"}`}>{summary}</span>
        <span className="chev">{open ? "收起 ▴" : "展开 ▾"}</span>
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
  const [context, setContext] = useState(false);
  return (
    <div className="evidence">
      <div className="evidence-meta">
        <span className="page-badge">p.{ev.page ?? "?"}</span>
        <span className="evidence-src">
          {paperTitle}
          {ev.section ? ` · ${ev.section}` : ""}
          {ev.kind === "table" && " · 表格"}
        </span>
        <button className="link" onClick={() => onOpenPdf({ paperId, page: ev.page || 1, boxes: ev.boxes, quote: ev.quote })}>
          查看原文 →
        </button>
      </div>
      <blockquote className="evidence-quote">{ev.quote}</blockquote>
      {ev.text && ev.text.length > ev.quote.length + 20 && (
        <>
          <button className="link small" onClick={() => setContext(!context)}>
            {context ? "收起上下文" : "展开上下文"}
          </button>
          {context && <Highlighted text={ev.text} quote={ev.quote} />}
        </>
      )}
    </div>
  );
}

function Highlighted({ text, quote }) {
  const t = text || "";
  const idx = quote ? t.toLowerCase().indexOf(quote.toLowerCase()) : -1;
  if (idx < 0) return <div className="para">{t}</div>;
  return (
    <div className="para">
      {t.slice(0, idx)}
      <mark>{t.slice(idx, idx + quote.length)}</mark>
      {t.slice(idx + quote.length)}
    </div>
  );
}

function ConditionTable({ pair, onOpenPdf, papersById }) {
  const fields = [...pair.fields].sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]);
  const differing = fields.filter((f) => f.severity !== "same");
  const same = fields.filter((f) => f.severity === "same");
  const markers = fields.flatMap((f) => f.markers.map((m) => ({ ...m, severity: f.severity })));
  const nameA = pair.a.subject || "结果 A";
  const nameB = pair.b.subject || "结果 B";

  return (
    <div className="pair">
      <div className="pair-title">
        <strong>{nameA}</strong> <span className="vs">vs</span> <strong>{nameB}</strong>
      </div>

      {markers.map((m) => (
        <div key={m.name} className={`callout ${SEVERITY_COLOR[m.severity]}`}>
          <div className="callout-title">关键差异 · {m.name}</div>
          <div className="callout-vs">
            <span>
              {nameA}：<b>{m.a}</b>
            </span>
            <span>
              {nameB}：<b>{m.b}</b>
            </span>
          </div>
          <div className="callout-reason">{m.reason}</div>
        </div>
      ))}

      {differing.length > 0 && (
        <div className="table-wrap">
          <table className="conditions">
            <thead>
              <tr>
                <th>条件</th>
                <th>{nameA}</th>
                <th>{nameB}</th>
                <th>判断</th>
              </tr>
            </thead>
            <tbody>
              {differing.map((f) => (
                <tr key={f.field} className={SEVERITY_COLOR[f.severity]}>
                  <td className="cond-name">{f.label}</td>
                  <td>
                    <Cond value={f.a} quote={f.a_quote} page={f.a_page} paperId={pair.a.paper_id} onOpenPdf={onOpenPdf} />
                  </td>
                  <td>
                    <Cond value={f.b} quote={f.b_quote} page={f.b_page} paperId={pair.b.paper_id} onOpenPdf={onOpenPdf} />
                  </td>
                  <td>
                    <span className={`tag ${SEVERITY_COLOR[f.severity]}`}>{SEVERITY_TEXT[f.severity]}</span>
                    {!f.markers.length && <div className="small muted reason">{f.reason}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {same.length > 0 && (
        <div className="same-row">
          <span className="tag green">一致</span>
          {same.map((f) => (
            <span key={f.field} className="same-item">
              {f.label} <b>{f.a}</b>
            </span>
          ))}
        </div>
      )}

      <div className="small muted">
        {[pair.a, pair.b]
          .filter((x) => x.paper_id)
          .map((x) => `${x.subject || "结果"} 出自《${papersById[x.paper_id]?.title || "论文"}》`)
          .filter((v, i, arr) => arr.indexOf(v) === i)
          .join("；")}
      </div>
    </div>
  );
}

function Cond({ value, quote, page, paperId, onOpenPdf }) {
  const [open, setOpen] = useState(false);
  if (!value) return <span className="muted">原文未写明</span>;
  return (
    <div className="cond">
      <strong>{value}</strong>
      {(quote || page) && (
        <div className="cond-actions">
          {quote && (
            <button className="link small" onClick={() => setOpen(!open)}>
              {open ? "收起原句" : "原句"}
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
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [state, setState] = useState("idle");
  if (state === "sent") return <div className="small muted feedback-row">✓ 已收到你的反馈，我们会用它改进规则。</div>;
  if (!open)
    return (
      <div className="feedback-row">
        <button className="link small muted-link" onClick={() => setOpen(true)}>
          觉得判错了？告诉我们
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
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="你认为系统哪里判错了？例如：两篇论文其实都用了 test-clean。"
        rows={2}
        autoFocus
      />
      <div className="disagree-actions">
        <button type="submit" className="small-btn" disabled={reason.trim().length < 2 || state === "sending"}>
          提交反馈
        </button>
        <button type="button" className="link" onClick={() => setOpen(false)}>
          取消
        </button>
        {state === "error" && <span className="error-inline">提交失败，请重试</span>}
      </div>
    </form>
  );
}
