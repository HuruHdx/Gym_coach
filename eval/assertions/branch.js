/**
 * 分支断言（v0.3）。期望写在 case 的 config 里。
 *
 * config:
 *   route / branch / reason: 单值或数组
 *   hit / queried / search_called / model_called: bool
 *   top_score_min / top_score_max / margin_max: number
 *   near_miss_min: number
 *   search_query_includes / search_query_excludes: string
 *   suggestions_min / suggestions_max: number
 *   suggestions_include / suggestions_exclude: string[]   按 label 子串匹配
 *   suggestions_empty: true
 *   sources_include / sources_exclude: string[]            按 source.ref / title 子串匹配（v0.3）
 *   sources_min: number
 *   sources_types: ["kb"|"rule"|"web"]                     只允许这些类型
 */
module.exports = (output, context) => {
  const c = (context && context.config) || {};
  const m = (context && context.metadata) || {};
  const kb = m.kb || {};
  const search = m.search || {};
  const opts = ((m.suggestions || [])).map((s) => String((s && s.label) || ''));
  const sources = Array.isArray(m.sources) ? m.sources : [];
  const sourceText = sources.map((s) => `${(s && s.type) || ''}:${(s && (s.ref || s.title)) || ''}`);
  const errs = [];

  const oneOf = (name, actual, expected) => {
    if (expected === undefined) return;
    const list = Array.isArray(expected) ? expected : [expected];
    if (!list.includes(actual)) errs.push(`${name}=${actual} ∉ ${list.join('|')}`);
  };

  oneOf('route', m.route, c.route);
  oneOf('branch', m.branch, c.branch);
  oneOf('reason', kb.reason, c.reason);
  if (c.hit !== undefined && kb.hit !== c.hit) errs.push(`kb.hit=${kb.hit}`);
  if (c.queried !== undefined && kb.queried !== c.queried) errs.push(`kb.queried=${kb.queried}`);
  if (c.search_called !== undefined && search.called !== c.search_called) {
    errs.push(`search.called=${search.called}`);
  }
  if (c.model_called !== undefined && m.model_called !== c.model_called) {
    errs.push(`model_called=${m.model_called}`);
  }
  if (c.top_score_min !== undefined && !(Number(kb.top_score) >= c.top_score_min)) {
    errs.push(`top_score=${kb.top_score} < ${c.top_score_min}`);
  }
  if (c.top_score_max !== undefined && !(Number(kb.top_score) <= c.top_score_max)) {
    errs.push(`top_score=${kb.top_score} > ${c.top_score_max}`);
  }
  if (c.margin_max !== undefined && !(Number(kb.margin) <= c.margin_max)) {
    errs.push(`margin=${kb.margin} > ${c.margin_max}`);
  }
  if (c.near_miss_min !== undefined && (kb.near_miss || []).length < c.near_miss_min) {
    errs.push(`near_miss=${(kb.near_miss || []).length} < ${c.near_miss_min}`);
  }

  const q = String(search.query || '');
  if (c.search_query_includes && !q.includes(c.search_query_includes)) errs.push(`search.query=${q}`);
  for (const bad of c.search_query_excludes || []) {
    if (q.includes(bad)) errs.push(`search.query_contains_${bad}`);
  }

  if (c.suggestions_empty && opts.length) errs.push(`suggestions=${opts.join('/')}`);
  if (c.suggestions_min !== undefined && opts.length < c.suggestions_min) {
    errs.push(`suggestions=${opts.length} < ${c.suggestions_min}`);
  }
  if (c.suggestions_max !== undefined && opts.length > c.suggestions_max) {
    errs.push(`suggestions=${opts.length} > ${c.suggestions_max}`);
  }
  for (const want of c.suggestions_include || []) {
    if (!opts.some((l) => l.includes(want))) errs.push(`suggestions_missing_${want}`);
  }
  for (const bad of c.suggestions_exclude || []) {
    if (opts.some((l) => l.includes(bad))) errs.push(`suggestions_has_${bad}`);
  }

  if (c.sources_min !== undefined && sources.length < c.sources_min) {
    errs.push(`sources=${sources.length} < ${c.sources_min}`);
  }
  for (const want of c.sources_include || []) {
    if (!sourceText.some((s) => s.includes(want))) errs.push(`sources_missing_${want}`);
  }
  for (const bad of c.sources_exclude || []) {
    if (sourceText.some((s) => s.includes(bad))) errs.push(`sources_has_${bad}`);
  }
  for (const t of c.sources_types || []) {
    if (!sources.length) errs.push('sources_empty');
    break;
  }
  if (c.sources_types) {
    for (const s of sources) {
      if (!c.sources_types.includes((s && s.type) || '')) errs.push(`source_type=${(s && s.type)}`);
    }
  }

  return {pass: errs.length === 0, score: errs.length ? 0 : 1, reason: errs.join('; ')};
};
