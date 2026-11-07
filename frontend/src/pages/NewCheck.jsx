import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { authorLine } from "../labels.js";
import { useAuth } from "../auth.jsx";

const MAX_CHARS = 1500;
const MAX_PAPERS = 5;
const EXAMPLE_TEXT =
  "Whisper 和 wav2vec 2.0 在 LibriSpeech 上都是 2.7%，所以准确率差不多。Whisper 是 OpenAI 在 2022 年提出的语音识别模型。";
const EXAMPLE_PAPER = "arXiv:2212.04356";

const SOURCE_CLASS = { published: "green", preprint: "yellow", not_found: "red", unknown: "yellow" };

const LAYERS = [
  { n: "①", title: "来源", text: "论文存在吗？正式发表还是预印本？" },
  { n: "②", title: "支持", text: "这句话的说法和数字，原文里有没有？" },
  { n: "③", title: "可比", text: "放在一起比较的两个结果，是同条件测的吗？", core: true },
];

export default function NewCheck() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [papers, setPapers] = useState([]);
  const [identifier, setIdentifier] = useState("");
  const [sentences, setSentences] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [health, setHealth] = useState(null);
  const [dragging, setDragging] = useState(false);
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

  async function onUpload(files) {
    let count = papers.length;
    for (const file of Array.from(files || [])) {
      if (count >= MAX_PAPERS) break;
      if (file.type && file.type !== "application/pdf") {
        setError(`${file.name} 不是 PDF。`);
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

  async function onSplit() {
    const result = await run("split", () => api.split(text));
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

  async function onExample() {
    setText(EXAMPLE_TEXT);
    setSentences(null);
    const paper = await run("paper", () => api.addIdentifier(EXAMPLE_PAPER));
    if (paper) addPaper(paper);
    const result = await run("split", () => api.split(EXAMPLE_TEXT));
    if (result) setSentences(result.sentences.map((s) => ({ ...s, selected: s.suggested })));
  }

  const toggle = (idx) => setSentences((list) => list.map((x) => (x.idx === idx ? { ...x, selected: !x.selected } : x)));

  const readyPapers = papers.filter((p) => p.fulltext_status === "ok");
  const processing = papers.some((p) => p.fulltext_status === "processing");
  const selectedCount = sentences?.filter((s) => s.selected).length || 0;
  const canSplit = text.trim() && text.length <= MAX_CHARS;
  const canStart = sentences && selectedCount > 0 && readyPapers.length > 0 && !processing;
  const full = papers.length >= MAX_PAPERS;

  const steps = [
    { label: "贴文字", done: !!text.trim() && text.length <= MAX_CHARS },
    { label: "加论文", done: readyPapers.length > 0 && !processing },
    { label: "确认句子", done: selectedCount > 0 },
  ];
  const blocker = !text.trim()
    ? "先贴一段要检查的文字"
    : text.length > MAX_CHARS
      ? `文字超过 ${MAX_CHARS} 字`
      : !papers.length
        ? "再添加至少一篇论文"
        : processing
          ? "论文还在读取中…"
          : !readyPapers.length
            ? "还没有读取到全文的论文"
            : !sentences
              ? "点击“识别句子”确认要检查哪些句子"
              : !selectedCount
                ? "至少选择一句"
                : null;

  return (
    <div className="new-check">
      <section className="hero">
        <h1>交给导师之前，先逐句核对一遍</h1>
        <p>贴一段 ChatGPT / Kimi 的回答或你自己写的综述，附上所引论文，CiteCheck 逐句给出三层检查结果，每条都附原文页码。</p>
        <div className="layer-intro">
          {LAYERS.map((l) => (
            <div key={l.n} className={`layer-chip ${l.core ? "core" : ""}`}>
              <span className="layer-n">{l.n}</span>
              <div>
                <strong>{l.title}</strong>
                {l.core && <em>核心</em>}
                <div>{l.text}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {health && (!health.ok || !health.llm) && (
        <div className="notice">
          {health.ok === false
            ? "连不上后端，请确认后端已启动（默认 http://localhost:8000）。"
            : "后端未配置大模型，正在使用规则模式：只能核对含数字的论断，条件抽取较粗。"}
        </div>
      )}

      <div className="compose">
        <div className="compose-main">
          <section className="card step-card">
            <div className="card-head">
              <h2>
                <StepBadge n={1} done={steps[0].done} /> 贴文字
              </h2>
              <button className="ghost small-btn" onClick={onExample} disabled={!!busy}>
                试试 Whisper 示例
              </button>
            </div>
            <textarea
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setSentences(null);
              }}
              placeholder="例如：Whisper 和 wav2vec 2.0 在 LibriSpeech 上都是 2.7%，所以准确率差不多。"
              rows={6}
            />
            <div className="field-foot">
              <span className="hint">中文、英文都可以；只检查你给出的论文，不判断观点本身对错。</span>
              <span className={`counter ${text.length > MAX_CHARS ? "over" : ""}`}>
                {text.length} / {MAX_CHARS}
              </span>
            </div>
          </section>

          <section className="card step-card">
            <div className="card-head">
              <h2>
                <StepBadge n={2} done={steps[1].done} /> 加论文
              </h2>
              <span className="hint">
                {papers.length} / {MAX_PAPERS} 篇
              </span>
            </div>
            <form onSubmit={onAddIdentifier} className="identifier-form">
              <input
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder="DOI、arXiv 编号或论文标题，例如 arXiv:2212.04356"
                disabled={full}
              />
              <button type="submit" disabled={!identifier.trim() || busy === "paper" || full}>
                添加
              </button>
            </form>
            <label
              className={`dropzone ${dragging ? "over" : ""} ${full ? "disabled" : ""}`}
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
                onChange={(e) => onUpload(e.target.files)}
                disabled={full}
              />
              <span className="drop-icon">⤓</span>
              <span>
                把 PDF 拖到这里，或<u>点击上传</u>
              </span>
              <span className="hint">填 DOI / arXiv 时会自动找开放全文，找不到再上传</span>
            </label>
            {busy === "paper" && <p className="hint">正在添加…</p>}
            {papers.length > 0 && (
              <ul className="paper-list">
                {papers.map((p) => (
                  <li key={p.id} className={`paper-card ${p.fulltext_status}`}>
                    <div className="paper-main">
                      <div className="paper-title">{p.title || "标题识别中…"}</div>
                      <div className="paper-meta">
                        {authorLine(p)} · {p.year || "年份未知"}
                        {p.venue ? ` · ${p.venue}` : ""}
                        {p.arxiv_id ? ` · arXiv:${p.arxiv_id}` : ""}
                      </div>
                      <div className="paper-tags">
                        <PaperStatus paper={p} />
                        {p.fulltext_status !== "processing" && (
                          <span className={`tag ${SOURCE_CLASS[p.source.status]}`}>① {p.source.label}</span>
                        )}
                      </div>
                      {p.warning && <div className="paper-warning">{p.warning}</div>}
                    </div>
                    <button
                      className="icon-btn"
                      title="移除"
                      onClick={() => setPapers((l) => l.filter((x) => x.id !== p.id))}
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {papers.length > 0 && <p className="hint">请确认识别出的标题、作者和年份无误。</p>}
          </section>

          <section className="card step-card">
            <div className="card-head">
              <h2>
                <StepBadge n={3} done={steps[2].done} /> 确认要检查的句子
              </h2>
              <button className={sentences ? "ghost small-btn" : "small-btn"} onClick={onSplit} disabled={!canSplit || busy === "split"}>
                {sentences ? "重新识别" : "识别句子"}
              </button>
            </div>
            {!sentences ? (
              <p className="hint">系统会拆句，并默认选中含有数字、比较或引用的句子。</p>
            ) : (
              <>
                <p className="hint">
                  点击句子可以选中 / 取消。已选 <strong>{selectedCount}</strong> / {sentences.length} 句。
                </p>
                <div className="sentence-flow">
                  {sentences.map((s) => (
                    <button
                      key={s.idx}
                      type="button"
                      className={`pick ${s.selected ? "on" : ""}`}
                      onClick={() => toggle(s.idx)}
                      title={[s.has_number && "含数字", s.has_comparison && "含比较", s.has_citation && "含引用"]
                        .filter(Boolean)
                        .join("、") || "未检测到可核对的内容"}
                    >
                      <span className="pick-box">{s.selected ? "✓" : ""}</span>
                      {s.text}
                      {(s.has_number || s.has_comparison || s.has_citation) && (
                        <span className="flags">
                          {s.has_number && <i>数字</i>}
                          {s.has_comparison && <i>比较</i>}
                          {s.has_citation && <i>引用</i>}
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
            <h3>准备情况</h3>
            <ol className="checklist">
              {steps.map((s, i) => (
                <li key={s.label} className={s.done ? "done" : ""}>
                  <span className="check-dot">{s.done ? "✓" : i + 1}</span>
                  {s.label}
                </li>
              ))}
            </ol>
            {error && <div className="error">{error}</div>}
            <button className="primary block" onClick={onStart} disabled={!canStart || busy === "start"}>
              {busy === "start" ? "正在提交…" : needLogin ? "登录后开始检查" : "开始检查"}
            </button>
            <p className="hint center">
              {blocker || `将检查 ${selectedCount} 句，对照 ${readyPapers.length} 篇论文，通常 1 分钟内完成`}
            </p>
            {user?.quota && <p className="hint center">本月剩余 {Math.max(0, user.quota - user.used)} 次</p>}
          </div>
        </aside>
      </div>
    </div>
  );
}

function StepBadge({ n, done }) {
  return <span className={`step ${done ? "done" : ""}`}>{done ? "✓" : n}</span>;
}

function PaperStatus({ paper }) {
  const map = {
    processing: ["blue", "读取全文中…"],
    ok: ["green", `已读取 ${paper.n_paragraphs} 段`],
    need_upload: ["yellow", "需要上传 PDF"],
    failed: ["red", "读取失败"],
    missing: ["yellow", "无全文"],
    stale: ["yellow", "需要重新读取"],
  };
  const [cls, label] = map[paper.fulltext_status] || ["yellow", paper.fulltext_status];
  return (
    <span className={`tag ${cls}`}>
      {paper.fulltext_status === "processing" && <span className="spinner" />}
      {label}
    </span>
  );
}
