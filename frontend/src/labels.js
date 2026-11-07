// 报告里用到的颜色、等级和“关键发现”。t / tx 来自 useI18n()。

export const SEVERITY_COLOR = { same: "green", unknown: "yellow", minor: "yellow", major: "red" };

// 标签优先用后端给的文字；英文界面下拿到中文时按结果代码显示，永远不会是空白
const FIELDS = ["dataset", "split", "metric", "baseline", "environment"];
export const sourceLabel = (item, t, tx) => tx(item.label, t(`src.${item.status}`));
export const verdictLabel = (r, t, tx) => tx(r.label, t(`verdict.${r.verdict}`));
export const levelLabel = (c, t, tx) => tx(c.label, t(`level.${c.level}`));
export const fieldLabel = (f, t, tx) => tx(f.label, t(FIELDS.includes(f.field) ? `field.${f.field}` : "field.other"));
export const markerName = (m, t, tx) => tx(m.name, t("marker.fallback"));
export const markerSide = (v, t, tx) => tx(v, t("find.notStated"));

export function authorLine(paper, t) {
  const authors = paper?.authors || [];
  if (!authors.length) return t("authors.none");
  return authors.length > 3 ? t("authors.etal", { names: authors.slice(0, 3).join(", ") }) : authors.join(", ");
}

const RANK = { red: 2, yellow: 1, green: 0 };
const SUPPORT_COLOR = { supported: "green", not_found: "yellow", contradicted: "red", number_mismatch: "red" };

// 把一句话三层结果里最值得看的几条提炼出来（红的在前），用于报告顶部和问题列表
export function keyFindings(sentence, t, tx) {
  if (!sentence || !sentence.support) return [];
  const out = [];
  for (const item of sentence.source?.items || []) {
    if (item.status === "not_found") out.push({ layer: "①", color: "red", text: t("find.notFound", { title: item.title || t("find.untitled") }) });
    else if (item.status === "preprint") out.push({ layer: "①", color: "yellow", text: t("find.preprint") });
    else if (item.status === "unknown") out.push({ layer: "①", color: "yellow", text: t("find.unknown") });
  }
  for (const r of sentence.support.results || []) {
    if (r.verdict === "supported") continue;
    const who = r.subject ? `${r.subject}: ` : "";
    const nums = r.verdict === "number_mismatch" && r.paper_value ? t("find.paperValue", { v: r.paper_value }) : "";
    out.push({ layer: "②", color: SUPPORT_COLOR[r.verdict], text: `${who}${verdictLabel(r, t, tx)}${nums}` });
  }
  const comp = sentence.comparability;
  if (comp && comp.level !== "na") {
    let unknown = 0;
    for (const pair of comp.pairs) {
      for (const f of pair.fields) {
        if (f.severity === "unknown") unknown += 1;
        if (f.severity !== "major" && f.severity !== "minor") continue;
        const m = f.markers?.[0];
        const what = m
          ? t("find.markerDiff", { name: markerName(m, t, tx), a: markerSide(m.a, t, tx), b: markerSide(m.b, t, tx) })
          : t("find.markerDiff", { name: fieldLabel(f, t, tx), a: f.a || t("find.notStated"), b: f.b || t("find.notStated") });
        out.push({ layer: "③", color: f.severity === "major" ? "red" : "yellow", text: what, reason: tx(m?.reason || f.reason) });
      }
    }
    if (unknown) out.push({ layer: "③", color: "yellow", text: t("find.unknownCount", { n: unknown }) });
  }
  return out.sort((a, b) => RANK[b.color] - RANK[a.color]);
}
