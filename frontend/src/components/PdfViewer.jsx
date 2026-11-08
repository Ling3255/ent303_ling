import { useEffect, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { api } from "../api.js";
import { useI18n } from "../i18n.jsx";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

const NO_BOXES = [];
const norm = (s) => (s || "").toLowerCase().replace(/[\s|]+/g, " ").replace(/[‐‑‒–—−]/g, "-").trim();

const tokens = (s) => norm(s).split(/[^a-z0-9.%]+/).filter((t) => t.length >= 2 || /\d/.test(t));

// 在页面文字层里找原句，返回需要高亮的矩形（画布坐标）。
// 简易解析（pypdf）和 PDF.js 的文字顺序不完全一样，所以按词重合度找最密集的一段文字，而不是精确匹配。
function findQuoteRects(textContent, viewport, quote) {
  const wanted = new Set(tokens(quote));
  if (wanted.size < 2) return [];
  const items = textContent.items.filter((it) => it.str && it.str.trim());
  const hit = items.map((it) => {
    const t = tokens(it.str);
    return t.length > 0 && t.filter((x) => wanted.has(x)).length / t.length >= 0.6;
  });
  let best = { score: 0, from: 0, to: -1 };
  for (let i = 0; i < items.length; i++) {
    if (!hit[i]) continue;
    const covered = new Set();
    let gap = 0;
    let last = i;
    for (let j = i; j < items.length && gap <= 2; j++) {
      if (hit[j]) {
        tokens(items[j].str).forEach((x) => wanted.has(x) && covered.add(x));
        last = j;
        gap = 0;
      } else gap++;
    }
    if (covered.size > best.score) best = { score: covered.size, from: i, to: last };
  }
  if (best.score < Math.max(3, wanted.size * 0.4)) return [];
  return items.slice(best.from, best.to + 1).map((item) => {
    const tx = pdfjsLib.Util.transform(viewport.transform, item.transform);
    const h = Math.hypot(tx[2], tx[3]);
    return { x: tx[4], y: tx[5] - h, w: item.width * viewport.scale, h: h * 1.15 };
  });
}

export default function PdfViewer({ paperId, paper, page: initialPage, boxes = NO_BOXES, quote, onClose }) {
  const { t } = useI18n();
  const canvasRef = useRef(null);
  const [doc, setDoc] = useState(null);
  const [page, setPage] = useState(initialPage || 1);
  const [scale, setScale] = useState(1.3);
  const [rects, setRects] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let destroyed = false;
    const task = pdfjsLib.getDocument(api.pdfUrl(paperId));
    task.promise.then(
      (d) => !destroyed && setDoc(d),
      () => !destroyed && setError("failed"),
    );
    return () => {
      destroyed = true;
      task.destroy();
    };
  }, [paperId]);

  useEffect(() => {
    if (!doc) return undefined;
    let cancelled = false;
    let renderTask;
    (async () => {
      const p = await doc.getPage(Math.min(Math.max(page, 1), doc.numPages));
      const viewport = p.getViewport({ scale });
      const canvas = canvasRef.current;
      if (!canvas || cancelled) return;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      renderTask = p.render({ canvasContext: canvas.getContext("2d"), viewport });
      await renderTask.promise.catch(() => {});
      if (cancelled) return;
      // GROBID 的段落 / 表格坐标画成淡色外框（表格的框往往很大）；
      // 原句本身在文字层里定位，画成紧贴文字的黄色高亮（表格就是那一行）
      const pageBoxes = boxes
        .filter((b) => b.page === page)
        .map((b) => ({ x: b.x * scale, y: b.y * scale, w: b.w * scale, h: b.h * scale, kind: "box" }));
      const content = await p.getTextContent();
      if (cancelled) return;
      const quoteRects = findQuoteRects(content, viewport, quote).map((r) => ({ ...r, kind: "quote" }));
      setRects([...pageBoxes, ...quoteRects]);
    })();
    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [doc, page, scale, boxes, quote]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={paper?.title || t("pdf.default")} onClick={(e) => e.stopPropagation()}>
        <div className="modal-bar">
          <strong className="modal-title">{paper?.title || t("pdf.default")}</strong>
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}>
            {t("pdf.prev")}
          </button>
          <span>
            {t("pdf.page", { p: page, n: doc?.numPages || "…" })}
          </span>
          <button onClick={() => setPage((p) => Math.min(doc?.numPages || p, p + 1))} disabled={!doc || page >= doc.numPages}>
            {t("pdf.next")}
          </button>
          <button onClick={() => setScale((s) => Math.max(0.6, s - 0.2))}>−</button>
          <button onClick={() => setScale((s) => Math.min(3, s + 0.2))}>＋</button>
          {page !== initialPage && <button onClick={() => setPage(initialPage)}>{t("pdf.back")}</button>}
          <button className="close" onClick={onClose}>
            {t("pdf.close")}
          </button>
        </div>
        {quote && <div className="modal-quote">
            {t("pdf.quote")}
            {quote}
          </div>}
        <div className="pdf-scroll">
          {error ? (
            <div className="error">{t("pdf.failed")}</div>
          ) : (
            <div className="pdf-page">
              <canvas ref={canvasRef} />
              {page === initialPage &&
                rects.map((r, i) => (
                  <div
                    key={i}
                    className={r.kind === "box" ? "pdf-box" : "pdf-highlight"}
                    style={{ left: r.x, top: r.y, width: r.w, height: r.h }}
                  />
                ))}
            </div>
          )}
          {!error && page === initialPage && quote && doc && !rects.some((r) => r.kind === "quote") && (
            <div className="hint">{t("pdf.notLocated")}</div>
          )}
        </div>
      </div>
    </div>
  );
}
