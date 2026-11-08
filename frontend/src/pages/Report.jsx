import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import { keyFindings } from "../labels.js";
import { useI18n } from "../i18n.jsx";
import SentenceDetail from "../components/SentenceDetail.jsx";

const PdfViewer = lazy(() => import("../components/PdfViewer.jsx"));
const COLOR_ORDER = { red: 0, yellow: 1, green: 2, gray: 3, none: 4 };

export default function Report() {
  const { id } = useParams();
  const { t, tx, locale } = useI18n();
  const [check, setCheck] = useState(null);
  const [error, setError] = useState("");
  const [active, setActive] = useState(null);
  const [filter, setFilter] = useState("all");
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
  const visible = useMemo(
    () => (filter === "all" ? checked : filter === "issues" ? issues : checked.filter((s) => s.color === filter)),
    [checked, filter, issues],
  );
  const visibleIds = useMemo(() => new Set(visible.map((s) => s.idx)), [visible]);

  const pick = useCallback((idx) => {
    setActive(idx);
    // 窄屏上详情在下方，选中后滚过去
    if (window.innerWidth < 960) detailRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  useEffect(() => {
    if (report && !visible.some((s) => s.idx === active)) setActive(visible[0]?.idx ?? null);
  }, [report, active, visible]);

  // ↑ / ↓ 在当前筛选结果之间切换
  useEffect(() => {
    const onKey = (e) => {
      if (pdf || !visible.length || ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp" && e.key !== "j" && e.key !== "k") return;
      e.preventDefault();
      const pos = visible.findIndex((s) => s.idx === active);
      const step = e.key === "ArrowDown" || e.key === "j" ? 1 : -1;
      const next = visible[Math.min(visible.length - 1, Math.max(0, pos + step))];
      if (next) setActive(next.idx);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visible, active, pdf]);

  if (error) return <div className="error" role="alert">{error}</div>;
  if (!check) return <div className="card skeleton">{t("rep.loading")}</div>;
  if (check.status === "failed")
    return (
      <div className="card narrow">
        <h2>{t("rep.failed")}</h2>
        <p className="error" role="alert">{check.error}</p>
        <Link to="/" className="button primary">
          {t("rep.retry")}
        </Link>
      </div>
    );
  if (!report) return <Progress check={check} />;

  const sentence = visible.find((s) => s.idx === active);
  const { summary } = report;
  const rulesMode = report.engine.claims === "rules" || report.engine.support.includes("rules");
  const selectFilter = (next) => {
    setFilter(next);
    const list = next === "all" ? checked : next === "issues" ? issues : checked.filter((s) => s.color === next);
    if (list.length && !list.some((s) => s.idx === active)) pick(list[0].idx);
  };
  const pickFromText = (idx) => {
    if (!visibleIds.has(idx)) setFilter("all");
    pick(idx);
  };
  const visibleIssues = visible.filter((s) => s.color === "red" || s.color === "yellow");

  return (
    <div className="report">
      <div className="report-head">
        <div>
          <h1>{t("rep.title")}</h1>
          <div className="muted small">
            {t("rep.meta", {
              time: new Date(check.created_at).toLocaleString(locale),
              n: checked.length,
              p: report.papers.length,
              s: summary.duration_s,
            })}
          </div>
        </div>
        <div className="head-actions">
          <Link to="/" className="button ghost">
            {t("rep.new")}
          </Link>
          <a className="button primary" href={`/checks/${id}/print`} target="_blank" rel="noreferrer">
            {t("rep.export")}
          </a>
        </div>
      </div>

      <div className="stats" role="group" aria-label={t("rep.filter")}>
        <StatChip color="red" n={summary.red} label={t("color.red")} active={filter === "red"} onClick={() => selectFilter("red")} />
        <StatChip color="yellow" n={summary.yellow} label={t("color.yellow")} active={filter === "yellow"} onClick={() => selectFilter("yellow")} />
        <StatChip color="green" n={summary.green} label={t("rep.stat.green")} active={filter === "green"} onClick={() => selectFilter("green")} />
        {summary.no_claim > 0 && <StatChip color="gray" n={summary.no_claim} label={t("color.gray")} active={filter === "gray"} onClick={() => selectFilter("gray")} />}
      </div>

      <div className="banner">
        <span>{tx(report.disclaimer)}</span>
        {rulesMode && <span className="banner-warn">{t("rep.rulesMode")}</span>}
      </div>

      <div className="report-filters">
        <div className="filter-buttons" role="group" aria-label={t("rep.filter")}>
          <button className={`filter-btn ${filter === "all" ? "active" : ""}`} onClick={() => selectFilter("all")} aria-pressed={filter === "all"}>
            {t("rep.filterAll", { n: checked.length })}
          </button>
          <button className={`filter-btn ${filter === "issues" ? "active" : ""}`} onClick={() => selectFilter("issues")} aria-pressed={filter === "issues"} disabled={!issues.length}>
            {t("rep.filterIssues", { n: issues.length })}
          </button>
        </div>
        <span className="filter-status" role="status">{t("rep.showing", { n: visible.length, total: checked.length })}</span>
      </div>

      <div className="columns">
        <div className="left-pane">
          <div className="card text-pane">
            <div className="pane-head">
              <h3>{t("rep.text")}</h3>
              <span className="hint kbd-hint">
                <kbd>↑</kbd>
                <kbd>↓</kbd> {t("rep.kbd")}
              </span>
            </div>
            <AnnotatedText text={check.text} sentences={report.sentences} active={active} onPick={pickFromText} numberOf={numberOf} visibleIds={visibleIds} />
            <div className="legend">
              {["red", "yellow", "green", "gray"].map((c) => (
                <span key={c}>
                  <span className={`dot ${c}`} /> {t(`color.${c}`)}
                </span>
              ))}
            </div>
          </div>

          {visibleIssues.length > 0 && (
            <div className="card issue-pane">
              <h3>{t("rep.issues", { n: visibleIssues.length })}</h3>
              <ul className="issue-list">
                {visibleIssues.map((s) => {
                  const top = keyFindings(s, t, tx)[0];
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
            <div className="card muted">{t("rep.pickHint")}</div>
          )}
        </div>
      </div>
      {pdf && (
        <Suspense fallback={<div className="modal-backdrop">{t("rep.openingPdf")}</div>}>
          <PdfViewer {...pdf} paper={papersById[pdf.paperId]} onClose={() => setPdf(null)} />
        </Suspense>
      )}
    </div>
  );
}

function StatChip({ color, n, label, active, onClick }) {
  return (
    <button className={`stat ${color} ${active ? "active" : ""}`} onClick={onClick} disabled={!n} aria-pressed={active}>
      <span className="stat-n">{n}</span>
      <span className="stat-label">
        <span className={`dot ${color}`} /> {label}
      </span>
    </button>
  );
}

function AnnotatedText({ text, sentences, active, onPick, numberOf, visibleIds }) {
  const { t } = useI18n();
  const pieces = [];
  let cursor = 0;
  for (const s of sentences) {
    if (s.start > cursor) pieces.push(<span key={`g${cursor}`}>{text.slice(cursor, s.start)}</span>);
    const clickable = s.selected;
    const dimmed = clickable && !visibleIds.has(s.idx);
    pieces.push(
      <span
        key={s.idx}
        className={`sent ${s.color} ${active === s.idx ? "active" : ""} ${clickable ? "clickable" : ""} ${dimmed ? "filtered-out" : ""}`}
        onClick={clickable ? () => onPick(s.idx) : undefined}
        onKeyDown={clickable ? (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onPick(s.idx);
          }
        } : undefined}
        role={clickable ? "button" : undefined}
        tabIndex={clickable ? 0 : undefined}
        aria-pressed={clickable ? active === s.idx : undefined}
        title={t(`color.${s.color}`)}
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

function Progress({ check }) {
  const { t, tx } = useI18n();
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 500);
    return () => clearInterval(timer);
  }, []);
  const current = Math.max(0, check.stages.findIndex((s) => s.key === check.stage));
  const pct = check.status === "queued" ? 4 : Math.round(((current + 0.5) / check.stages.length) * 100);
  return (
    <div className="card progress">
      <h2>{t("prog.title")}</h2>
      <div className="bar" role="progressbar" aria-label={t("prog.title")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
        <div className="bar-fill" style={{ width: `${pct}%` }} />
      </div>
      <ol className="stages">
        {check.stages.map((s, i) => (
          <li key={s.key} className={i < current ? "done" : i === current && check.status !== "queued" ? "current" : ""} aria-current={i === current && check.status !== "queued" ? "step" : undefined}>
            <span className="stage-dot">{i < current ? "✓" : i + 1}</span>
            <div>
              <div>{tx(s.label, t(`stage.${s.key}`))}</div>
              <div className="hint">{t(`prog.${s.key}`)}</div>
            </div>
          </li>
        ))}
      </ol>
      <p className="hint center">{t("prog.elapsed", { s: elapsed })}</p>
    </div>
  );
}
