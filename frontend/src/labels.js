export const COLOR_TEXT = {
  green: "没问题",
  yellow: "需要注意",
  red: "可能影响结论",
  gray: "无可核对论断",
  none: "未检查",
};

export const LAYER_NAMES = {
  source: "① 来源",
  support: "② 支持",
  comparability: "③ 可比",
};

export const SEVERITY_TEXT = {
  same: "一致",
  unknown: "原文未写明",
  minor: "有差异，通常不影响",
  major: "有差异，可能影响结论",
};

export const SEVERITY_COLOR = { same: "green", unknown: "yellow", minor: "yellow", major: "red" };

export function authorLine(paper) {
  const authors = paper?.authors || [];
  if (!authors.length) return "作者未识别";
  return authors.length > 3 ? `${authors.slice(0, 3).join(", ")} 等` : authors.join(", ");
}

const RANK = { red: 2, yellow: 1, green: 0 };
const SUPPORT_COLOR = { supported: "green", not_found: "yellow", contradicted: "red", number_mismatch: "red" };

// 把一句话三层结果里最值得看的几条提炼出来（红的在前），用于报告顶部和问题列表
export function keyFindings(sentence) {
  if (!sentence || !sentence.support) return [];
  const out = [];
  for (const item of sentence.source?.items || []) {
    if (item.status === "not_found") out.push({ layer: "①", color: "red", text: `找不到论文《${item.title || "未识别"}》` });
    else if (item.status === "preprint") out.push({ layer: "①", color: "yellow", text: "只找到预印本，未查到正式发表版本" });
    else if (item.status === "unknown") out.push({ layer: "①", color: "yellow", text: "来源查询失败，请稍后重试" });
  }
  for (const r of sentence.support.results || []) {
    if (r.verdict === "supported") continue;
    const who = r.subject ? `${r.subject}：` : "";
    const nums = r.verdict === "number_mismatch" && r.paper_value ? `（原文为 ${r.paper_value}）` : "";
    out.push({ layer: "②", color: SUPPORT_COLOR[r.verdict], text: `${who}${r.label}${nums}` });
  }
  const comp = sentence.comparability;
  if (comp && comp.level !== "na") {
    let unknown = 0;
    for (const pair of comp.pairs) {
      for (const f of pair.fields) {
        if (f.severity === "unknown") unknown += 1;
        if (f.severity !== "major" && f.severity !== "minor") continue;
        const m = f.markers?.[0];
        const what = m ? `${m.name}不同：${m.a} vs ${m.b}` : `${f.label}不同：${f.a || "未写明"} vs ${f.b || "未写明"}`;
        out.push({ layer: "③", color: f.severity === "major" ? "red" : "yellow", text: what, reason: m?.reason || f.reason });
      }
    }
    if (unknown) out.push({ layer: "③", color: "yellow", text: `${unknown} 项条件原文未写明，无法确认可比` });
  }
  return out.sort((a, b) => RANK[b.color] - RANK[a.color]);
}
