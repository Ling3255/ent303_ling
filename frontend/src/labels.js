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
