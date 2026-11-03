/**
 * 引用断言（v0.2）：引用了哪一条，回答的肌群用词有没有跟被引条目一致。
 *
 * v0.2 起 hits[].target 是契约字段（词表中文，如「上背」），优先用它；
 * 没有就退回解析 snippet 里的「目标肌：X」（兼容老实现）。
 *
 * config:
 *   exactly_one: true
 *   any_of / all_of / none_of: id 列表
 *   empty: true                           citations 必须为空（knowledge/compare/ask/search）
 *   target_muscle: true                   回答必须含被引条目的 target 词
 *   extra_muscles: ["上背","背阔肌"]       与 target 竞争的词；答成另一条就会命中
 */
module.exports = (output, context) => {
  const c = (context && context.config) || {};
  const m = (context && context.metadata) || {};
  const cites = ((m.citations || [])).map(String);
  const hits = ((m.kb && m.kb.hits) || []).slice();
  const text = String(output || '');
  const errs = [];

  if (c.exactly_one && cites.length !== 1) errs.push(`citations=${cites.length}`);
  if (c.empty && cites.length) errs.push(`citations_should_be_empty=${cites.join(',')}`);
  if (c.any_of && !cites.some((x) => c.any_of.map(String).includes(x))) {
    errs.push(`citations=${cites.join(',')} ∉ ${c.any_of.join('|')}`);
  }
  if (c.all_of) {
    const missing = c.all_of.map(String).filter((x) => !cites.includes(x));
    if (missing.length) errs.push(`missing_citation=${missing.join(',')}`);
  }
  for (const bad of c.none_of || []) {
    if (cites.includes(String(bad))) errs.push(`forbidden_citation=${bad}`);
  }

  if (c.target_muscle) {
    const cited = hits.find((h) => String(h.id) === cites[0]) || {};
    const match = /(?:目标肌|目标肌肉)[：:]\s*([^（(]+)/.exec(String(cited.snippet || ''));
    const target = String(cited.target || (match && match[1]) || '').trim();
    if (!target) {
      errs.push('cited_hit_has_no_target');
    } else {
      if (!text.includes(target)) errs.push(`answer_missing_${target}`);
      const rivals = (c.extra_muscles || []).filter((w) => w && w !== target && text.includes(w));
      if (rivals.length) errs.push(`answer_says_${rivals.join('+')}_but_cited_${target}`);
    }
  }

  return {pass: errs.length === 0, score: errs.length ? 0 : 1, reason: errs.join('; ')};
};
