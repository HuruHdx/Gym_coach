/**
 * 意图断言（metadata.intent）：agent / muscles / focus_exercises / rewrite。
 *
 * config:
 *   agent: "coach_chat" | ["coach_chat","coach_plan"]
 *   muscles: ["背"]                      集合相等（顺序无关）；[] 表示必须为空
 *   muscles_include / muscles_exclude: []
 *   focus_exercises: ["深蹲"]             集合相等
 *   focus_exercises_empty: true
 *   focus_exercises_include / focus_exercises_exclude: []
 *   rewrite_contains: "划船"
 */
module.exports = (output, context) => {
  const c = (context && context.config) || {};
  const intent = ((context && context.metadata && context.metadata.intent) || {});
  const muscles = (intent.muscles || []).slice();
  const focus = (intent.focus_exercises || []).slice();
  const errs = [];

  if (c.agent !== undefined) {
    const list = Array.isArray(c.agent) ? c.agent : [c.agent];
    if (!list.includes(intent.agent)) errs.push(`agent=${intent.agent}`);
  }
  if (c.muscles !== undefined) {
    const want = c.muscles.slice().sort().join(',');
    const got = muscles.slice().sort().join(',');
    if (want !== got) errs.push(`muscles=[${got}] want=[${want}]`);
  }
  for (const m of c.muscles_include || []) {
    if (!muscles.includes(m)) errs.push(`muscles_missing=${m}`);
  }
  for (const m of c.muscles_exclude || []) {
    if (muscles.includes(m)) errs.push(`muscles_has=${m}`);
  }
  if (c.focus_exercises !== undefined) {
    const want = c.focus_exercises.slice().sort().join(',');
    const got = focus.slice().sort().join(',');
    if (want !== got) errs.push(`focus=[${got}] want=[${want}]`);
  }
  if (c.focus_exercises_empty && focus.length) errs.push(`focus=[${focus.join(',')}]`);
  for (const f of c.focus_exercises_include || []) {
    if (!focus.includes(f)) errs.push(`focus_missing=${f}`);
  }
  for (const f of c.focus_exercises_exclude || []) {
    if (focus.includes(f)) errs.push(`focus_has=${f}`);
  }
  if (c.rewrite_contains && !String(intent.rewrite || '').includes(c.rewrite_contains)) {
    errs.push(`rewrite=${intent.rewrite}`);
  }

  return {pass: errs.length === 0, score: errs.length ? 0 : 1, reason: errs.join('; ')};
};
