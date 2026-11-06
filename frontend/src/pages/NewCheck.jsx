import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { authorLine } from "../labels.js";

const MAX_CHARS = 1500;
const MAX_PAPERS = 5;
const EXAMPLE_TEXT =
  "Whisper 和 wav2vec 2.0 在 LibriSpeech 上都是 2.7%，所以准确率差不多。Whisper 是 OpenAI 在 2022 年提出的语音识别模型。";
const EXAMPLE_PAPER = "arXiv:2212.04356";

const SOURCE_CLASS = { published: "green", preprint: "yellow", not_found: "red", unknown: "yellow" };

export default function NewCheck() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [papers, setPapers] = useState([]);
  const [identifier, setIdentifier] = useState("");
  const [sentences, setSentences] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [health, setHealth] = useState(null);
  const fileInput = useRef(null);

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
    for (const file of Array.from(files || [])) {
      if (papers.length >= MAX_PAPERS) break;
      const paper = await run("paper", () => api.upload(file));
      if (paper) addPaper(paper);
    }
    if (fileInput.current) fileInput.current.value = "";
  }

  async function onSplit() {
    const result = await run("split", () => api.split(text));
    if (result) setSentences(result.sentences.map((s) => ({ ...s, selected: s.suggested })));
  }

  async function onStart() {
    const result = await run("start", () =>
      api.createCheck({
        text,
        paper_ids: papers.map((p) => p.id),
        sentences: sentences.map((s) => ({ idx: s.idx, selected: s.selected })),
      }),
    );
    if (result) navigate(`/checks/${result.id}`);
  }

  async function onExample() {
    setText(EXAMPLE_TEXT);
    setSentences(null);
    const paper = await run("paper", () => api.addIdentifier(EXAMPLE_PAPER));
    if (paper) addPaper(paper);
  }

  const readyPapers = papers.filter((p) => p.fulltext_status === "ok");
  const processing = papers.some((p) => p.fulltext_status === "processing");
  const selectedCount = sentences?.filter((s) => s.selected).length || 0;
  const canSplit = text.trim() && text.length <= MAX_CHARS;
  const canStart = sentences && selectedCount > 0 && readyPapers.length > 0 && !processing;

  return (
    <div className="new-check">
      {health && (!health.ok || !health.llm) && (
        <div className="notice">
          {health.ok === false
            ? "连不上后端，请确认后端已启动（默认 http://localhost:8000）。"
            : "后端未配置大模型，正在使用规则模式：只能核对含数字的论断，条件抽取较粗。配置 LLM_API_KEY 后效果更好。"}
        </div>
      )}

      <section className="card">
        <div className="card-head">
          <h2>
            <span className="step">1</span> 贴文字
          </h2>
          <button className="link" onClick={onExample} disabled={!!busy}>
            填入 Whisper 示例
          </button>
        </div>
        <p className="hint">ChatGPT / Kimi 的回答、AI 整理的综述，或你自己写的段落。中文、英文都可以。</p>
        <textarea
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setSentences(null);
          }}
          placeholder="例如：Whisper 和 wav2vec 2.0 在 LibriSpeech 上都是 2.7%，所以准确率差不多。"
          rows={7}
        />
        <div className={`counter ${text.length > MAX_CHARS ? "over" : ""}`}>
          {text.length} / {MAX_CHARS} 字
        </div>
      </section>

      <section className="card">
        <h2>
          <span className="step">2</span> 加论文 <small>（最多 {MAX_PAPERS} 篇）</small>
        </h2>
        <p className="hint">填 DOI 或 arXiv 编号会自动去 arXiv 和开放获取渠道找全文；找不到时请上传 PDF。</p>
        <div className="paper-inputs">
          <form onSubmit={onAddIdentifier} className="identifier-form">
            <input
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder="DOI / arXiv 编号 / 论文标题，例如 arXiv:2212.04356"
              disabled={papers.length >= MAX_PAPERS}
            />
            <button type="submit" disabled={!identifier.trim() || busy === "paper" || papers.length >= MAX_PAPERS}>
              添加
            </button>
          </form>
          <span className="or">或</span>
          <label className={`upload ${papers.length >= MAX_PAPERS ? "disabled" : ""}`}>
            上传 PDF
            <input
              ref={fileInput}
              type="file"
              accept="application/pdf"
              multiple
              onChange={(e) => onUpload(e.target.files)}
              disabled={papers.length >= MAX_PAPERS}
            />
          </label>
        </div>
        {busy === "paper" && <p className="hint">正在添加…</p>}
        <ul className="paper-list">
          {papers.map((p) => (
            <li key={p.id} className="paper-card">
              <div className="paper-main">
                <div className="paper-title">{p.title || "（标题识别中）"}</div>
                <div className="paper-meta">
                  {authorLine(p)} · {p.year || "年份未知"}
                  {p.venue ? ` · ${p.venue}` : ""}
                  {p.arxiv_id ? ` · arXiv:${p.arxiv_id}` : ""}
                  {p.doi ? ` · DOI ${p.doi}` : ""}
                </div>
                {p.warning && <div className="paper-warning">{p.warning}</div>}
              </div>
              <div className="paper-side">
                <PaperStatus paper={p} />
                {p.fulltext_status !== "processing" && (
                  <span className={`tag ${SOURCE_CLASS[p.source.status]}`}>来源：{p.source.label}</span>
                )}
                <button className="link danger" onClick={() => setPapers((l) => l.filter((x) => x.id !== p.id))}>
                  移除
                </button>
              </div>
            </li>
          ))}
        </ul>
        {papers.length > 0 && <p className="hint">请确认上面识别出的标题、作者和年份无误。</p>}
      </section>

      <section className="card">
        <div className="card-head">
          <h2>
            <span className="step">3</span> 确认要检查的句子
          </h2>
          <button onClick={onSplit} disabled={!canSplit || busy === "split"}>
            {sentences ? "重新拆句" : "拆句"}
          </button>
        </div>
        <p className="hint">系统高亮含有数字、比较或引用的句子并默认勾选，你可以取消或加选。</p>
        {sentences && (
          <ol className="sentence-pick">
            {sentences.map((s) => (
              <li key={s.idx} className={s.selected ? "on" : ""}>
                <label>
                  <input
                    type="checkbox"
                    checked={s.selected}
                    onChange={() =>
                      setSentences((list) => list.map((x) => (x.idx === s.idx ? { ...x, selected: !x.selected } : x)))
                    }
                  />
                  <span className={s.suggested ? "suggested" : ""}>{s.text}</span>
                </label>
                <span className="flags">
                  {s.has_number && <i>数字</i>}
                  {s.has_comparison && <i>比较</i>}
                  {s.has_citation && <i>引用</i>}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>

      {error && <div className="error">{error}</div>}

      <div className="actions">
        <span className="hint">
          {!sentences
            ? "先完成第 3 步拆句。"
            : processing
              ? "论文还在读取中…"
              : !readyPapers.length
                ? "至少需要一篇已读取全文的论文。"
                : `将检查 ${selectedCount} 句，对照 ${readyPapers.length} 篇论文。`}
        </span>
        <button className="primary" onClick={onStart} disabled={!canStart || busy === "start"}>
          开始检查
        </button>
      </div>
    </div>
  );
}

function PaperStatus({ paper }) {
  const map = {
    processing: ["blue", "读取中…"],
    ok: ["green", `已读取 ${paper.n_paragraphs} 段`],
    need_upload: ["yellow", "需要上传 PDF"],
    failed: ["red", "读取失败"],
    missing: ["yellow", "无全文"],
  };
  const [cls, label] = map[paper.fulltext_status] || ["yellow", paper.fulltext_status];
  return <span className={`tag ${cls}`}>{label}</span>;
}
