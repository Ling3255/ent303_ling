import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import { COLOR_TEXT } from "../labels.js";
import SentenceDetail from "../components/SentenceDetail.jsx";

const PdfViewer = lazy(() => import("../components/PdfViewer.jsx"));

export default function Report() {
  const { id } = useParams();
  const [check, setCheck] = useState(null);
  const [error, setError] = useState("");
  const [active, setActive] = useState(null);
  const [pdf, setPdf] = useState(null); // {paperId, page, boxes, quote}

  useEffect(() => {
    let timer;
    let cancelled = false;
    async function poll() {
      try {
        const data = await api.check(id);
        if (cancelled) return;
        setCheck(data);
        if (data.status === "queued" || data.status === "running") timer = setTimeout(poll, 1000);
      } catch (e) {
        if (!cancelled) setError(e.message);
      }
    }
    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id]);

  const report = check?.report;
  const papersById = useMemo(() => Object.fromEntries((report?.papers || []).map((p) => [p.id, p])), [report]);

  // 默认选中第一句有问题的句子
  useEffect(() => {
    if (report && active === null) {
      const first =
        report.sentences.find((s) => s.color === "red") ||
        report.sentences.find((s) => s.color === "yellow") ||
        report.sentences.find((s) => s.selected);
      if (first) setActive(first.idx);
    }
  }, [report, active]);

  if (error) return <div className="error">{error}</div>;
  if (!check) return <div className="card">加载中…</div>;
  if (check.status === "failed")
    return (
      <div className="card">
        <h2>检查失败</h2>
        <p className="error">{check.error}</p>
        <Link to="/">返回重新检查</Link>
      </div>
    );
  if (!report) return <Progress check={check} />;

  const sentence = report.sentences.find((s) => s.idx === active);
  const { summary } = report;

  return (
    <div className="report">
      <div className="report-head">
        <div className="summary">
          <span className="dot green" /> {summary.green} 句没问题
          <span className="dot yellow" /> {summary.yellow} 句需要注意
          <span className="dot red" /> {summary.red} 句可能影响结论
          {summary.no_claim > 0 && <span className="muted">· {summary.no_claim} 句无可核对论断</span>}
          <span className="muted">· 用时 {summary.duration_s} 秒</span>
        </div>
        <div className="head-actions">
          <Link to="/" className="button">
            新的检查
          </Link>
          <a className="button primary" href={`/checks/${id}/print`} target="_blank" rel="noreferrer">
            导出证据单
          </a>
        </div>
      </div>
      <div className="disclaimer">{report.disclaimer}</div>
      {(report.engine.claims === "rules" || report.engine.support.includes("rules")) && (
        <div className="notice">本次使用规则模式（未调用大模型），结果仅供参考，请重点核对原文。</div>
      )}

      <div className="columns">
        <div className="text-pane card">
          <h3>原文字</h3>
          <AnnotatedText text={check.text} sentences={report.sentences} active={active} onPick={setActive} />
          <div className="legend">
            {["green", "yellow", "red", "gray"].map((c) => (
              <span key={c}>
                <span className={`dot ${c}`} /> {COLOR_TEXT[c]}
              </span>
            ))}
          </div>
        </div>
        <div className="detail-pane">
          {sentence ? (
            <SentenceDetail
              key={sentence.idx}
              checkId={id}
              sentence={sentence}
              papersById={papersById}
              onOpenPdf={setPdf}
            />
          ) : (
            <div className="card muted">点击左侧的一句话查看三层结果。</div>
          )}
        </div>
      </div>
      {pdf && (
        <Suspense fallback={<div className="modal-backdrop">正在打开 PDF…</div>}>
          <PdfViewer {...pdf} paper={papersById[pdf.paperId]} onClose={() => setPdf(null)} />
        </Suspense>
      )}
    </div>
  );
}

function AnnotatedText({ text, sentences, active, onPick }) {
  const pieces = [];
  let cursor = 0;
  for (const s of sentences) {
    if (s.start > cursor) pieces.push(<span key={`g${cursor}`}>{text.slice(cursor, s.start)}</span>);
    const clickable = s.selected;
    pieces.push(
      <span
        key={s.idx}
        className={`sent ${s.color} ${active === s.idx ? "active" : ""} ${clickable ? "clickable" : ""}`}
        onClick={clickable ? () => onPick(s.idx) : undefined}
        title={COLOR_TEXT[s.color]}
      >
        {text.slice(s.start, s.end)}
      </span>,
    );
    cursor = s.end;
  }
  if (cursor < text.length) pieces.push(<span key="tail">{text.slice(cursor)}</span>);
  return <div className="annotated">{pieces}</div>;
}

function Progress({ check }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const t = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 500);
    return () => clearInterval(t);
  }, []);
  const current = check.stages.findIndex((s) => s.key === check.stage);
  return (
    <div className="card progress">
      <h2>正在检查…</h2>
      <ol className="stages">
        {check.stages.map((s, i) => (
          <li key={s.key} className={i < current ? "done" : i === current ? "current" : ""}>
            <span className="stage-dot">{i < current ? "✓" : i + 1}</span> {s.label}
          </li>
        ))}
      </ol>
      <p className="hint">已用 {elapsed} 秒，通常 60 秒内完成。</p>
    </div>
  );
}
