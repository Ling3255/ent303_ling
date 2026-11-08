import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { authorLine, sourceLabel } from "../labels.js";
import { useAuth } from "../auth.jsx";
import { useI18n } from "../i18n.jsx";

const MAX_CHARS = 1500;
const MAX_PAPERS = 5;
const EXAMPLES = [
  {
    id: "speech",
    label: "home.exampleSpeech",
    paper: "arXiv:2212.04356",
    text: {
      zh: "Whisper 和 wav2vec 2.0 在 LibriSpeech 上都是 2.7%，所以准确率差不多。Whisper 是 OpenAI 在 2022 年提出的语音识别模型。",
      en: "Whisper and wav2vec 2.0 both reach 2.7% on LibriSpeech, so their accuracy is about the same. Whisper is a speech recognition model proposed by OpenAI in 2022.",
    },
  },
  {
    id: "image",
    label: "home.exampleImage",
    paper: "arXiv:1512.03385",
    text: {
      zh: "ResNet-50 和 VGG-16 在 ImageNet 上的 top-1 错误率相近，所以它们在各种图像分类场景中的准确率都差不多。",
      en: "ResNet-50 and VGG-16 have similar top-1 error rates on ImageNet, so their accuracy is about the same across image classification settings.",
    },
  },
  {
    id: "rag",
    label: "home.exampleRag",
    paper: "arXiv:2005.11401",
    text: {
      zh: "RAG-Token 和 RAG-Sequence 在 Natural Questions 上的 F1 接近，所以两种生成方式的效果相同。",
      en: "RAG-Token and RAG-Sequence achieve similar F1 scores on Natural Questions, so both generation strategies are equally effective.",
    },
  },
];

const SOURCE_CLASS = { published: "green", preprint: "yellow", not_found: "red", unknown: "yellow" };

export default function NewCheck() {
  const navigate = useNavigate();
  const { t, tx, lang } = useI18n();
  const [text, setText] = useState("");
  const [papers, setPapers] = useState([]);
  const [identifier, setIdentifier] = useState("");
  const [sentences, setSentences] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [health, setHealth] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [exampleId, setExampleId] = useState("");
  const fileInput = useRef(null);
  const { user, config, openLogin, refresh } = useAuth();
  const needLogin = config?.required && !user;

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ ok: false }));
  }, []);

  // 论文在后台读取，处理中的论文每 1.5 秒刷新一次
  useEffect(() => {
    const pending = papers.filter((p) => p.fulltext_status === "processing");
    if (!pending.length) return undefined;
    const timer = setTimeout(async () => {
      const fresh = await Promise.all(pending.map((p) => api.paper(p.id).catch(() => p)));
      setPapers((list) => list.map((p) => fresh.find((f) => f.id === p.id) || p));
    }, 1500);
    return () => clearTimeout(timer);
  }, [papers]);

  const addPaper = (paper) =>
    setPapers((list) => (list.some((p) => p.id === paper.id) ? list : [...list, paper]));

  async function run(label, fn) {
    setError("");
    setBusy(label);
    try {
      return await fn();
    } catch (e) {
      if (e.status === 401) openLogin();
      setError(e.message);
      return null;
    } finally {
      setBusy("");
    }
  }

  async function onAddIdentifier(e) {
    e?.preventDefault();
    const value = identifier.trim();
    if (!value) return;
    const paper = await run("paper", () => api.addIdentifier(value));
    if (paper) {
      addPaper(paper);
      setIdentifier("");
    }
  }

  async function retryPaper(paper) {
    const value = paper.arxiv_id ? `arXiv:${paper.arxiv_id}` : paper.doi;
    if (!value) return;
    const fresh = await run(`retry-${paper.id}`, () => api.addIdentifier(value));
    if (fresh) {
      setPapers((list) => [...list.filter((p) => p.id !== paper.id && p.id !== fresh.id), fresh]);
      setSentences(null);
    }
  }

  async function onUpload(files) {
    let count = papers.length;
    for (const file of Array.from(files || [])) {
      if (count >= MAX_PAPERS) break;
      if (file.type && file.type !== "application/pdf") {
        setError(t("home.notPdf", { name: file.name }));
        continue;
      }
      const paper = await run("paper", () => api.upload(file));
      if (paper) {
        addPaper(paper);
        count += 1;
      }
    }
    if (fileInput.current) fileInput.current.value = "";
  }

  async function splitText(value) {
    const result = await run("split", () => api.split(value));
    if (result) setSentences(result.sentences.map((s) => ({ ...s, selected: s.suggested })));
  }

  async function onStart() {
    if (needLogin) return openLogin();
    const result = await run("start", () =>
      api.createCheck({
        text,
        paper_ids: papers.map((p) => p.id),
        sentences: sentences.map((s) => ({ idx: s.idx, selected: s.selected })),
      }),
    );
    if (result) {
      refresh();
      navigate(`/checks/${result.id}`);
    }
  }

  async function onExample(example) {
    const exampleText = example.text[lang];
    setExampleId(example.id);
    setText(exampleText);
    setPapers([]);
    setSentences(null);
    const paper = await run("paper", () => api.addIdentifier(example.paper));
    if (paper) addPaper(paper);
    await splitText(exampleText);
  }

  const toggle = (idx) => setSentences((list) => list.map((x) => (x.idx === idx ? { ...x, selected: !x.selected } : x)));

  const readyPapers = papers.filter((p) => p.fulltext_status === "ok");
  const processing = papers.some((p) => p.fulltext_status === "processing");
  const selectedCount = sentences?.filter((s) => s.selected).length || 0;
  const canSplit = text.trim() && text.length <= MAX_CHARS;
  const canStart = sentences && selectedCount > 0 && readyPapers.length > 0 && !processing;
  const full = papers.length >= MAX_PAPERS;

  const steps = [
    { label: t("home.step1"), done: !!text.trim() && text.length <= MAX_CHARS },
    { label: t("home.step2"), done: readyPapers.length > 0 && !processing },
    { label: t("home.step3"), done: selectedCount > 0 },
  ];
  const blocker = !text.trim()
    ? t("home.block.noText")
    : text.length > MAX_CHARS
      ? t("home.block.tooLong", { max: MAX_CHARS })
      : !papers.length
        ? t("home.block.noPaper")
        : processing
          ? t("home.block.processing")
          : !readyPapers.length
            ? t("home.block.noReady")
            : !sentences
              ? t("home.block.noSplit")
              : !selectedCount
                ? t("home.block.noSelected")
                : null;

  const layers = [
    { n: "①", title: t("home.l1.title"), text: t("home.l1.text") },
    { n: "②", title: t("home.l2.title"), text: t("home.l2.text") },
    { n: "③", title: t("home.l3.title"), text: t("home.l3.text"), core: true },
  ];

  return (
    <div className="new-check">
      <section className="hero">
        <h1>{t("home.hero")}</h1>
        <p>{t("home.heroSub")}</p>
        <div className="layer-intro">
          {layers.map((l) => (
            <div key={l.n} className={`layer-chip ${l.core ? "core" : ""}`}>
              <span className="layer-n">{l.n}</span>
              <div>
                <strong>{l.title}</strong>
                {l.core && <em>{t("home.core")}</em>}
                <div>{l.text}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {health && (!health.ok || !health.llm) && (
        <div className="notice" role="status">{health.ok === false ? t("home.noBackend") : t("home.rulesMode")}</div>
      )}

      <div className="compose">
        <div className="compose-main">
          <section className="card step-card">
            <div className="card-head example-card-head">
              <h2>
                <StepBadge n={1} done={steps[0].done} /> {t("home.step1")}
              </h2>
              <div className="example-picker" role="group" aria-label={t("home.exampleGroup")}>
                {EXAMPLES.map((example) => (
                  <button
                    key={example.id}
                    type="button"
                    className={`ghost small-btn example-option ${exampleId === example.id ? "active" : ""}`}
                    onClick={() => onExample(example)}
                    disabled={!!busy}
                    aria-pressed={exampleId === example.id}
                  >
                    {t(example.label)}
                  </button>
                ))}
              </div>
            </div>
            <textarea
              value={text}
              aria-label={t("home.step1")}
              onChange={(e) => {
                setText(e.target.value);
                setExampleId("");
                setSentences(null);
              }}
              placeholder={t("home.textPlaceholder")}
              rows={6}
            />
            <div className="field-foot">
              <span className="hint">{t("home.textHint")}</span>
              <span className={`counter ${text.length > MAX_CHARS ? "over" : ""}`}>
                {text.length} / {MAX_CHARS}
              </span>
            </div>
          </section>

          <section className="card step-card">
            <div className="card-head">
              <h2>
                <StepBadge n={2} done={steps[1].done} /> {t("home.step2")}
              </h2>
              <span className="hint">{t("home.paperCount", { n: papers.length, max: MAX_PAPERS })}</span>
            </div>
            <form onSubmit={onAddIdentifier} className="identifier-form">
              <input
                value={identifier}
                aria-label={t("home.step2")}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder={t("home.idPlaceholder")}
                disabled={full}
              />
              <button type="submit" disabled={!identifier.trim() || busy === "paper" || full}>
                {t("home.add")}
              </button>
            </form>
            <label
              className={`dropzone ${dragging ? "over" : ""} ${full ? "disabled" : ""}`}
              tabIndex={full ? -1 : 0}
              onKeyDown={(e) => {
                if (!full && (e.key === "Enter" || e.key === " ")) {
                  e.preventDefault();
                  fileInput.current?.click();
                }
              }}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                if (!full) onUpload(e.dataTransfer.files);
              }}
            >
              <input
                ref={fileInput}
                type="file"
                accept="application/pdf"
                multiple
                tabIndex={-1}
                onChange={(e) => onUpload(e.target.files)}
                disabled={full}
              />
              <span className="drop-icon">⤓</span>
              <span>
                {t("home.drop")}
                <u>{t("home.dropClick")}</u>
              </span>
              <span className="hint">{t("home.dropHint")}</span>
            </label>
            {busy === "paper" && <p className="hint" role="status">{t("home.adding")}</p>}
            {papers.length > 0 && (
              <ul className="paper-list">
                {papers.map((p) => (
                  <li key={p.id} className={`paper-card ${p.fulltext_status}`}>
                    <div className="paper-main">
                      <div className="paper-title">{p.title || t("home.titlePending")}</div>
                      <div className="paper-meta">
                        {authorLine(p, t)} · {p.year || t("home.yearUnknown")}
                        {p.venue ? ` · ${p.venue}` : ""}
                        {p.arxiv_id ? ` · arXiv:${p.arxiv_id}` : ""}
                      </div>
                      <div className="paper-tags">
                        <PaperStatus paper={p} />
                        {p.fulltext_status !== "processing" && (
                          <span className={`tag ${SOURCE_CLASS[p.source.status]}`}>① {sourceLabel(p.source, t, tx)}</span>
                        )}
                      </div>
                      {p.warning && <div className="paper-warning">{tx(p.warning)}</div>}
                    </div>
                    <div className="paper-actions">
                      {["failed", "stale"].includes(p.fulltext_status) && (p.arxiv_id || p.doi) && (
                        <button
                          type="button"
                          className="link small"
                          onClick={() => retryPaper(p)}
                          disabled={busy === `retry-${p.id}`}
                        >
                          {busy === `retry-${p.id}` ? t("home.retrying") : t("home.retry")}
                        </button>
                      )}
                      <button
                        type="button"
                        className="icon-btn"
                        title={t("home.remove")}
                        aria-label={`${t("home.remove")}: ${p.title || t("home.titlePending")}`}
                        onClick={() => setPapers((l) => l.filter((x) => x.id !== p.id))}
                      >
                        ×
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {papers.length > 0 && <p className="hint">{t("home.confirmMeta")}</p>}
          </section>

          <section className="card step-card">
            <div className="card-head">
              <h2>
                <StepBadge n={3} done={steps[2].done} /> {t("home.step3")}
              </h2>
              <button
                className={sentences ? "ghost small-btn" : "small-btn"}
                onClick={() => splitText(text)}
                disabled={!canSplit || busy === "split"}
              >
                {busy === "split" ? t("home.splitting") : sentences ? t("home.resplit") : t("home.split")}
              </button>
            </div>
            {!sentences ? (
              <p className="hint">{t("home.splitHint")}</p>
            ) : (
              <>
                <p className="hint">{t("home.pickHint", { n: selectedCount, total: sentences.length })}</p>
                <div className="sentence-flow">
                  {sentences.map((s) => (
                    <button
                      key={s.idx}
                      type="button"
                      className={`pick ${s.selected ? "on" : ""}`}
                      onClick={() => toggle(s.idx)}
                      aria-pressed={s.selected}
                      title={
                        [
                          s.has_number && t("home.flagNumberTitle"),
                          s.has_comparison && t("home.flagComparisonTitle"),
                          s.has_citation && t("home.flagCitationTitle"),
                        ]
                          .filter(Boolean)
                          .join(", ") || t("home.flagNone")
                      }
                    >
                      <span className="pick-box">{s.selected ? "✓" : ""}</span>
                      {s.text}
                      {(s.has_number || s.has_comparison || s.has_citation) && (
                        <span className="flags">
                          {s.has_number && <i>{t("home.flagNumber")}</i>}
                          {s.has_comparison && <i>{t("home.flagComparison")}</i>}
                          {s.has_citation && <i>{t("home.flagCitation")}</i>}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </>
            )}
          </section>
        </div>

        <aside className="compose-side">
          <div className="card side-card">
            <h3>{t("home.ready")}</h3>
            <ol className="checklist">
              {steps.map((s, i) => (
                <li key={i} className={s.done ? "done" : ""}>
                  <span className="check-dot">{s.done ? "✓" : i + 1}</span>
                  {s.label}
                </li>
              ))}
            </ol>
            {error && <div className="error" role="alert">{error}</div>}
            <button className="primary block" onClick={onStart} disabled={!canStart || busy === "start"}>
              {busy === "start" ? t("home.starting") : needLogin ? t("home.loginToStart") : t("home.start")}
            </button>
            <p className="hint center" aria-live="polite">{blocker || t("home.willCheck", { n: selectedCount, p: readyPapers.length })}</p>
            {user?.quota && <p className="hint center">{t("home.quotaLeft", { n: Math.max(0, user.quota - user.used) })}</p>}
          </div>
        </aside>
      </div>
    </div>
  );
}

function StepBadge({ n, done }) {
  return <span className={`step ${done ? "done" : ""}`}>{done ? "✓" : n}</span>;
}

const PAPER_STATUS_CLASS = { processing: "blue", ok: "green", need_upload: "yellow", failed: "red", missing: "yellow", stale: "yellow" };

function PaperStatus({ paper }) {
  const { t } = useI18n();
  const status = paper.fulltext_status;
  const label = PAPER_STATUS_CLASS[status] ? t(`paper.${status}`, { n: paper.n_paragraphs }) : status;
  return (
    <span className={`tag ${PAPER_STATUS_CLASS[status] || "yellow"}`} role="status">
      {status === "processing" && <span className="spinner" />}
      {label}
    </span>
  );
}
