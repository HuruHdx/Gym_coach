/**
 * 回答文本断言（用户可见的 answer）。
 *
 * config:
 *   contains: ["上背"]                 全部要出现
 *   not_contains: ["背阔肌"]           一个都不能出现
 *   not_regex: ["\\d+\\s*kg"]          不能匹配
 *   any_of: ["上背","背阔肌"]          至少出现一个
 *   min_chars / max_chars: number      中文字数区间
 *   zh_ratio_min: 0.7                  中文字符占比下限（英文源条目回退时用）
 *   english_run_max: 5                 连续英文单词上限（防整句英文）
 *   forbid_weight: true                不得出现「xx kg / 公斤」这类具体重量
 *   forbid_json: true                  不得露出 JSON/提示词残留
 */
module.exports = (output, context) => {
  const c = (context && context.config) || {};
  const text = String(output == null ? '' : output);
  const errs = [];

  for (const word of c.contains || []) {
    if (!text.includes(word)) errs.push(`missing=${word}`);
  }
  for (const word of c.not_contains || []) {
    if (text.includes(word)) errs.push(`forbidden=${word}`);
  }
  for (const re of c.not_regex || []) {
    if (new RegExp(re, 'i').test(text)) errs.push(`matched=${re}`);
  }
  if (c.any_of && c.any_of.length && !c.any_of.some((w) => text.includes(w))) {
    errs.push(`none_of=${c.any_of.join('|')}`);
  }
  if (c.min_chars !== undefined && text.length < c.min_chars) errs.push(`len=${text.length}`);
  if (c.max_chars !== undefined && text.length > c.max_chars) errs.push(`len=${text.length}`);

  if (c.forbid_weight && /\d+(?:\.\d+)?\s*(?:kg|公斤|千克|KG)/i.test(text)) {
    errs.push('claims_specific_weight');
  }
  if (c.forbid_json && /[{}]|"text"\s*:|【CHAT】|【INTENT_REWRITE】/.test(text)) {
    errs.push('leaks_json_or_prompt');
  }

  if (c.zh_ratio_min !== undefined) {
    const zh = (text.match(/[\u4e00-\u9fff]/g) || []).length;
    const en = (text.match(/[A-Za-z]{2,}/g) || []).length;
    const ratio = zh + en === 0 ? 0 : zh / (zh + en);
    if (ratio < c.zh_ratio_min) errs.push(`zh_ratio=${ratio.toFixed(2)}`);
  }
  if (c.english_run_max !== undefined) {
    const run = /(?:[A-Za-z][A-Za-z'-]*\s+){3,}[A-Za-z][A-Za-z'-]*/g;
    const hits = text.match(run) || [];
    const worst = hits.reduce((n, s) => Math.max(n, s.split(/\s+/).length), 0);
    if (worst > c.english_run_max) errs.push(`english_run=${worst}`);
  }

  return {pass: errs.length === 0, score: errs.length ? 0 : 1, reason: errs.join('; ')};
};
