/**
 * 数据类断言：工具层 + 结果层（不写死数字）。
 *
 * 工具层：有没有查、过滤条件对不对、命中哪条
 * 结果层：答案里的数字必须等于 stats.hits 里的值
 *
 * config:
 *   queried: true|false          stats.queried
 *   hits_empty: true             夹具里没有这条
 *   hits_min: 1                  至少几条命中
 *   hit_name_includes: "卧推"    命中里要有这个名字
 *   muscles_include: ["胸"]      过滤部位
 *   tool_called: "get_related_stats"
 *   value_from_first_hit: true   答案必须出现 hits[0].last_weight
 *   max_chars / min_chars
 */
module.exports = (output, context) => {
  const c = (context && context.config) || {};
  const m = (context && context.metadata) || {};
  const s = m.stats || {};
  const hits = Array.isArray(s.hits) ? s.hits : [];
  const filter = s.filter || {};
  const calls = Array.isArray(s.tool_calls) ? s.tool_calls : [];
  const text = String(output || '');
  const errs = [];

  if (c.queried !== undefined && Boolean(s.queried) !== c.queried) {
    errs.push(`stats.queried=${s.queried}`);
  }
  if (c.hits_empty && hits.length) errs.push(`hits=${hits.length}（应为空）`);
  if (c.hits_min !== undefined && hits.length < c.hits_min) errs.push(`hits=${hits.length}`);

  if (c.hit_name_includes) {
    const names = hits.map((h) => String((h && h.name) || ''));
    if (!names.some((n) => n.includes(c.hit_name_includes))) {
      errs.push(`hits 无「${c.hit_name_includes}」: ${names.join('/') || '空'}`);
    }
  }
  for (const mu of c.muscles_include || []) {
    const muscles = Array.isArray(filter.muscles) ? filter.muscles : [];
    if (!muscles.includes(mu)) errs.push(`filter.muscles 无「${mu}」`);
  }
  if (c.tool_called && !calls.some((t) => (t && t.tool) === c.tool_called)) {
    errs.push(`未调用 ${c.tool_called}`);
  }

  if (c.value_from_first_hit) {
    const hit = hits[0] || {};
    const v = hit.last_weight;
    if (v === null || v === undefined) {
      errs.push('hits[0] 无 last_weight');
    } else if (!text.includes(String(v))) {
      errs.push(`答案未出现工具返回值 ${v}`);
    }
  }

  if (c.min_chars !== undefined && text.length < c.min_chars) errs.push(`len=${text.length}`);
  if (c.max_chars !== undefined && text.length > c.max_chars) errs.push(`len=${text.length}`);

  return {pass: errs.length === 0, score: errs.length ? 0 : 1, reason: errs.join('; ')};
};
