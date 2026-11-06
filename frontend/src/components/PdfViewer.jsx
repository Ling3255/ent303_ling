import { useEffect, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { api } from "../api.js";

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
      () => !destroyed && setError("PDF 无法打开：可能已过 7 天保留期被删除，请重新上传。"),
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
      // GROBID 给了段落坐标就直接画框；否则在文字层里搜原句
      const pageBoxes = boxes.filter((b) => b.page === page);
      if (pageBoxes.length) {
        setRects(pageBoxes.map((b) => ({ x: b.x * scale, y: b.y * scale, w: b.w * scale, h: b.h * scale })));
      } else {
        const content = await p.getTextContent();
        if (!cancelled) setRects(findQuoteRects(content, viewport, quote));
      }
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
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-bar">
          <strong className="modal-title">{paper?.title || "论文原文"}</strong>
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1}>
            上一页
          </button>
          <span>
            第 {page} / {doc?.numPages || "…"} 页
          </span>
          <button onClick={() => setPage((p) => Math.min(doc?.numPages || p, p + 1))} disabled={!doc || page >= doc.numPages}>
            下一页
          </button>
          <button onClick={() => setScale((s) => Math.max(0.6, s - 0.2))}>−</button>
          <button onClick={() => setScale((s) => Math.min(3, s + 0.2))}>＋</button>
          {page !== initialPage && <button onClick={() => setPage(initialPage)}>回到引文页</button>}
          <button className="close" onClick={onClose}>
            关闭
          </button>
        </div>
        {quote && <div className="modal-quote">引文：{quote}</div>}
        <div className="pdf-scroll">
          {error ? (
            <div className="error">{error}</div>
          ) : (
            <div className="pdf-page">
              <canvas ref={canvasRef} />
              {page === initialPage &&
                rects.map((r, i) => (
                  <div key={i} className="pdf-highlight" style={{ left: r.x, top: r.y, width: r.w, height: r.h }} />
                ))}
            </div>
          )}
          {!error && page === initialPage && quote && doc && rects.length === 0 && (
            <div className="hint">没能在这一页自动定位原句，请在页面中查找上方的引文。</div>
          )}
        </div>
      </div>
    </div>
  );
}
