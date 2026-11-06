import { useState } from "react";
import { api } from "../api.js";
import { COLOR_TEXT, LAYER_NAMES, SEVERITY_COLOR, SEVERITY_TEXT } from "../labels.js";

const SUPPORT_COLOR = { supported: "green", not_found: "yellow", contradicted: "red", number_mismatch: "red" };
const SOURCE_COLOR = { published: "green", preprint: "yellow", unknown: "yellow", not_found: "red" };

export default function SentenceDetail({ checkId, sentence, papersById, onOpenPdf }) {
  if (sentence.color === "gray") {
    return (
      <div className="card">
        <blockquote className="quoted">{sentence.text}</blockquote>
        <p className="muted">{sentence.note}</p>
      </div>
    );
  }
  const { source, support, comparability } = sentence;
  const paperTitle = (pid) => papersById[pid]?.title || "论文";

  return (
    <div className="detail">
      <div className="card">
        <div className="sentence-head">
          <span className={`tag ${sentence.color}`}>{COLOR_TEXT[sentence.color]}</span>
        </div>
        <blockquote className="quoted">{sentence.text}</blockquote>
      </div>

      <Layer
        name="source"
        title={LAYER_NAMES.source}
        color={source.color}
        summary={source.items.map((i) => i.label).join(" / ")}
        checkId={checkId}
        sentence={sentence}
      >
        <ul className="plain">
          {source.items.map((item) => {
            const p = papersById[item.paper_id];
            return (
              <li key={item.paper_id}>
                <span className={`tag ${SOURCE_COLOR[item.status]}`}>{item.label}</span> {item.title || "未识别标题"}
                {p?.venue && item.status === "published" && <span className="muted"> · {p.venue}</span>}
                {item.status === "preprint" && <span className="muted"> · 只找到预印本，未查到正式发表版本</span>}
                {item.status === "unknown" && <span className="muted"> · 学术数据接口查询失败，请稍后重试</span>}
              </li>
            );
          })}
        </ul>
      </Layer>

      <Layer
        name="support"
        title={LAYER_NAMES.support}
        color={support.color}
        summary={support.label}
        checkId={checkId}
        sentence={sentence}
      >
        {support.results.map((r) => (
          <div key={r.claim_id} className="claim">
            <div className="claim-head">
              <span className={`tag ${SUPPORT_COLOR[r.verdict]}`}>{r.label}</span>
              <strong>{r.subject || "论断"}</strong>
              {r.values?.length > 0 && <span className="muted">文字中的数字：{r.values.join("、")}</span>}
              {r.paper_value && <span className="muted">原文数字：{r.paper_value}</span>}
            </div>
            {r.statement !== sentence.text && <div className="muted small">{r.statement}</div>}
            {r.explanation && <p>{r.explanation}</p>}
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
                检索到的候选段落在第{" "}
                {[...new Set(r.candidates.map((c) => c.page).filter(Boolean))].slice(0, 5).join("、")} 页，可
                <button
                  className="link"
                  onClick={() => onOpenPdf({ paperId: r.paper_id, page: r.candidates[0].page || 1, boxes: [] })}
                >
                  打开 PDF
                </button>
                自行核对。
              </div>
            )}
          </div>
        ))}
      </Layer>

      <Layer
        name="comparability"
        title={LAYER_NAMES.comparability}
        color={comparability.color}
        summary={comparability.label}
        checkId={checkId}
        sentence={sentence}
      >
        {comparability.level === "na" ? (
          <p className="muted">这句话没有把两个结果放在一起比较，不做可比检查。</p>
        ) : (
          comparability.pairs.map((pair, i) => (
            <ConditionTable key={i} pair={pair} papersById={papersById} onOpenPdf={onOpenPdf} />
          ))
        )}
        {comparability.level === "consistent" && (
          <p className="note">未发现条件差异。这不代表两个结果一定可以直接比较，请核对原文。</p>
        )}
      </Layer>
    </div>
  );
}

function Layer({ name, title, color, summary, children, checkId, sentence }) {
  const [open, setOpen] = useState(true);
  return (
    <section className={`card layer ${color || "neutral"}`}>
      <header onClick={() => setOpen(!open)}>
        <h3>{title}</h3>
        <span className={`tag ${color || "neutral"}`}>{summary}</span>
        <span className="chev">{open ? "▾" : "▸"}</span>
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
  return (
    <div className="evidence">
      <div className="evidence-meta">
        {paperTitle} · 第 {ev.page ?? "?"} 页{ev.section ? ` · ${ev.section}` : ""}
        {ev.kind === "table" && " · 表格"}
        <button className="link" onClick={() => onOpenPdf({ paperId, page: ev.page || 1, boxes: ev.boxes, quote: ev.quote })}>
          查看原文
        </button>
      </div>
      <Highlighted text={ev.text} quote={ev.quote} />
    </div>
  );
}

export function Highlighted({ text, quote }) {
  const t = text || "";
  const idx = quote ? t.toLowerCase().indexOf(quote.toLowerCase()) : -1;
  if (idx < 0) {
    return (
      <div className="para">
        {quote && <mark>{quote}</mark>}
        {quote && t && <div className="para-context">{t.slice(0, 400)}{t.length > 400 ? "…" : ""}</div>}
        {!quote && t}
      </div>
    );
  }
  const start = Math.max(0, idx - 200);
  const end = Math.min(t.length, idx + quote.length + 200);
  return (
    <div className="para">
      {start > 0 && "…"}
      {t.slice(start, idx)}
      <mark>{t.slice(idx, idx + quote.length)}</mark>
      {t.slice(idx + quote.length, end)}
      {end < t.length && "…"}
    </div>
  );
}

function ConditionTable({ pair, papersById, onOpenPdf }) {
  return (
    <div className="pair">
      <table className="conditions">
        <thead>
          <tr>
            <th>条件</th>
            <th>{pair.a.subject || "结果 A"}</th>
            <th>{pair.b.subject || "结果 B"}</th>
            <th>判断</th>
          </tr>
        </thead>
        <tbody>
          {pair.fields.map((f) => (
            <tr key={f.field} className={SEVERITY_COLOR[f.severity]}>
              <td>{f.label}</td>
              <td>
                <Cond value={f.a} quote={f.a_quote} page={f.a_page} paperId={pair.a.paper_id} onOpenPdf={onOpenPdf} />
              </td>
              <td>
                <Cond value={f.b} quote={f.b_quote} page={f.b_page} paperId={pair.b.paper_id} onOpenPdf={onOpenPdf} />
              </td>
              <td>
                <span className={`tag ${SEVERITY_COLOR[f.severity]}`}>{SEVERITY_TEXT[f.severity]}</span>
                {f.severity !== "same" && <div className="small muted">{f.reason}</div>}
                {f.markers.map((m) => (
                  <div key={m.name} className="small">
                    {m.name}：{m.a} vs {m.b}
                  </div>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="small muted">
        {[pair.a, pair.b]
          .filter((x) => x.paper_id)
          .map((x) => `${x.subject || "结果"} 出自《${papersById[x.paper_id]?.title || "论文"}》`)
          .join("；")}
      </div>
    </div>
  );
}

function Cond({ value, quote, page, paperId, onOpenPdf }) {
  if (!value) return <span className="muted">原文未写明</span>;
  return (
    <div>
      <strong>{value}</strong>
      {quote && <div className="quote-small">“{quote.length > 160 ? quote.slice(0, 160) + "…" : quote}”</div>}
      {page && paperId && (
        <button className="link small" onClick={() => onOpenPdf({ paperId, page, boxes: [], quote })}>
          第 {page} 页
        </button>
      )}
    </div>
  );
}

function Disagree({ checkId, sentence, layer, label }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [state, setState] = useState("idle");
  if (state === "sent") return <div className="small muted">已收到你的反馈，谢谢！我们会用它改进规则。</div>;
  if (!open)
    return (
      <button className="link small" onClick={() => setOpen(true)}>
        不同意？
      </button>
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
      />
      <div>
        <button type="submit" disabled={reason.trim().length < 2 || state === "sending"}>
          提交
        </button>
        <button type="button" className="link" onClick={() => setOpen(false)}>
          取消
        </button>
        {state === "error" && <span className="error-inline">提交失败，请重试</span>}
      </div>
    </form>
  );
}
