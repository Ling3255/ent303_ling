import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import { COLOR_TEXT, keyFindings } from "../labels.js";
import SentenceDetail from "../components/SentenceDetail.jsx";

const PdfViewer = lazy(() => import("../components/PdfViewer.jsx"));
const COLOR_ORDER = { red: 0, yellow: 1, green: 2, gray: 3, none: 4 };

export default function Report() {
  const { id } = useParams();
  const [check, setCheck] = useState(null);
  const [error, setError] = useState("");
  const [active, setActive] = useState(null);
  const [pdf, setPdf] = useState(null); // {paperId, page, boxes, quote}
  const detailRef = useRef(null);

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
  const checked = useMemo(() => (report?.sentences || []).filter((s) => s.selected), [report]);
  // 句子编号只给检查过的句子，和问题列表一致
  const numberOf = useMemo(() => Object.fromEntries(checked.map((s, i) => [s.idx, i + 1])), [checked]);
  const issues = useMemo(
    () =>
      checked
        .filter((s) => s.color === "red" || s.color === "yellow")
        .sort((a, b) => COLOR_ORDER[a.color] - COLOR_ORDER[b.color] || a.idx - b.idx),
    [checked],
  );

  const pick = useCallback((idx) => {
    setActive(idx);
    // 窄屏上详情在下方，选中后滚过去
    if (window.innerWidth < 960) detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  // 默认选中最严重的一句
  useEffect(() => {
    if (report && active === null) {
      const first = issues[0] || checked[0];
      if (first) setActive(first.idx);
    }
  }, [report, active, issues, checked]);

  // ↑ / ↓ 在检查过的句子之间切换
  useEffect(() => {
    const onKey = (e) => {
      if (pdf || !checked.length || ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp" && e.key !== "j" && e.key !== "k") return;
      e.preventDefault();
      const pos = checked.findIndex((s) => s.idx === active);
      const step = e.key === "ArrowDown" || e.key === "j" ? 1 : -1;
      const next = checked[Math.min(checked.length - 1, Math.max(0, pos + step))];
      if (next) setActive(next.idx);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [checked, active, pdf]);

  if (error) return <div className="error">{error}</div>;
  if (!check) return <div className="card skeleton">加载中…</div>;
  if (check.status === "failed")
    return (
      <div className="card narrow">
        <h2>检查失败</h2>
        <p className="error">{check.error}</p>
        <Link to="/" className="button primary">
          返回重新检查
        </Link>
      </div>
    );
  if (!report) return <Progress check={check} />;

  const sentence = report.sentences.find((s) => s.idx === active);
  const { summary } = report;
  const rulesMode = report.engine.claims === "rules" || report.engine.support.includes("rules");
  const jumpTo = (color) => {
    const s = checked.find((x) => x.color === color);
    if (s) pick(s.idx);
  };

  return (
    <div className="report">
      <div className="report-head">
        <div>
          <h1>检查报告</h1>
          <div className="muted small">
            {new Date(check.created_at).toLocaleString("zh-CN")} · 检查 {checked.length} 句 · 对照 {report.papers.length} 篇论文 · 用时{" "}
            {summary.duration_s} 秒
          </div>
        </div>
        <div className="head-actions">
          <Link to="/" className="button ghost">
            新的检查
          </Link>
          <a className="button primary" href={`/checks/${id}/print`} target="_blank" rel="noreferrer">
            导出证据单
          </a>
        </div>
      </div>

      <div className="stats">
        <StatChip color="red" n={summary.red} label="可能影响结论" onClick={() => jumpTo("red")} />
        <StatChip color="yellow" n={summary.yellow} label="需要注意" onClick={() => jumpTo("yellow")} />
        <StatChip color="green" n={summary.green} label="没发现问题" onClick={() => jumpTo("green")} />
        {summary.no_claim > 0 && <StatChip color="gray" n={summary.no_claim} label="无可核对论断" onClick={() => jumpTo("gray")} />}
      </div>

      <div className="banner">
        <span>{report.disclaimer}</span>
        {rulesMode && <span className="banner-warn">本次为规则模式（未调用大模型），请重点核对原文。</span>}
      </div>

      <div className="columns">
        <div className="left-pane">
          <div className="card text-pane">
            <div className="pane-head">
              <h3>原文字</h3>
              <span className="hint kbd-hint">
                <kbd>↑</kbd>
                <kbd>↓</kbd> 切换句子
              </span>
            </div>
            <AnnotatedText text={check.text} sentences={report.sentences} active={active} onPick={pick} numberOf={numberOf} />
            <div className="legend">
              {["red", "yellow", "green", "gray"].map((c) => (
                <span key={c}>
                  <span className={`dot ${c}`} /> {COLOR_TEXT[c]}
                </span>
              ))}
            </div>
          </div>

          {issues.length > 0 && (
            <div className="card issue-pane">
              <h3>需要关注（{issues.length}）</h3>
              <ul className="issue-list">
                {issues.map((s) => {
                  const top = keyFindings(s)[0];
                  return (
                    <li key={s.idx}>
                      <button className={`issue ${s.color} ${active === s.idx ? "active" : ""}`} onClick={() => pick(s.idx)}>
                        <span className={`num ${s.color}`}>{numberOf[s.idx]}</span>
                        <span className="issue-body">
                          <span className="issue-text">{s.text}</span>
                          {top && (
                            <span className="issue-why">
                              {top.layer} {top.text}
                            </span>
                          )}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>

        <div className="detail-pane" ref={detailRef}>
          {sentence ? (
            <SentenceDetail
              key={sentence.idx}
              number={numberOf[sentence.idx]}
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

function StatChip({ color, n, label, onClick }) {
  return (
    <button className={`stat ${color}`} onClick={onClick} disabled={!n}>
      <span className="stat-n">{n}</span>
      <span className="stat-label">
        <span className={`dot ${color}`} /> {label}
      </span>
    </button>
  );
}

function AnnotatedText({ text, sentences, active, onPick, numberOf }) {
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
        {clickable && <sup className={`sent-num ${s.color}`}>{numberOf[s.idx]}</sup>}
        {text.slice(s.start, s.end)}
      </span>,
    );
    cursor = s.end;
  }
  if (cursor < text.length) pieces.push(<span key="tail">{text.slice(cursor)}</span>);
  return <div className="annotated">{pieces}</div>;
}

const STAGE_HINTS = {
  reading: "解析论文结构、页码和表格",
  retrieving: "识别论断，在论文中找对应段落",
  extracting: "核对说法和数字，抽取数据集、划分、指标等条件",
  comparing: "逐项对照被比较结果的测试条件",
};

function Progress({ check }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const t = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 500);
    return () => clearInterval(t);
  }, []);
  const current = Math.max(0, check.stages.findIndex((s) => s.key === check.stage));
  const pct = check.status === "queued" ? 4 : Math.round(((current + 0.5) / check.stages.length) * 100);
  return (
    <div className="card progress">
      <h2>正在检查…</h2>
      <div className="bar">
        <div className="bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <ol className="stages">
        {check.stages.map((s, i) => (
          <li key={s.key} className={i < current ? "done" : i === current && check.status !== "queued" ? "current" : ""}>
            <span className="stage-dot">{i < current ? "✓" : i + 1}</span>
            <div>
              <div>{s.label}</div>
              <div className="hint">{STAGE_HINTS[s.key]}</div>
            </div>
          </li>
        ))}
      </ol>
      <p className="hint center">已用 {elapsed} 秒，通常 1 分钟内完成。可以离开此页，稍后用同一链接查看结果。</p>
    </div>
  );
}
