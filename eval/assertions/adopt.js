/**
 * 采纳断言：看最后一张草稿真的落库后是什么样。
 *
 * 只在用例带 adopt_after 时有意义。检查的是「卡片 → SetLog」这一步有没有走歪：
 * 组数是否按 meta.sets 展开、动作数是否一致、改稿删掉的动作有没有真的消失。
 *
 * config：
 *   set_count_min / set_count_max  落库组数范围
 *   set_count_matches_last_card    落库组数 == 卡片里各动作 meta.sets 之和（缺省按 3 组）
 *   exercises_exact                动作名单必须完全一致
 *   exercises_has                  动作名单至少包含（子串匹配）
 *   exercises_none                 动作名单必须不含（子串匹配，改稿删除用这个）
 *   exercises_min / exercises_max  动作个数范围
 *   status                         期望 session 状态（默认 active）
 */
module.exports = (output, context) => {
  const c = (context && context.config) || {};
  const m = (context && context.metadata) || {};
  const a = m.adopted;

  if (!a) {
    return { pass: false, score: 0, reason: '没有 adopted（用例缺 adopt_after 或采纳失败）' };
  }

  const errs = [];
  const status = c.status || 'active';
  if (a.status !== status) errs.push(`status=${a.status} want=${status}`);

  if (c.set_count_min !== undefined && a.set_count < c.set_count_min) {
    errs.push(`组数 ${a.set_count} < ${c.set_count_min}`);
  }
  if (c.set_count_max !== undefined && a.set_count > c.set_count_max) {
    errs.push(`组数 ${a.set_count} > ${c.set_count_max}`);
  }

  // 「组数按 meta.sets 展开」不能靠拍下限：直接拿最后一张卡的 sets 求和对照
  if (c.set_count_matches_last_card) {
    const turns = m.turns || [];
    const last = turns.filter((t) => t && t.card_title && (t.card_items_meta || []).length).pop();
    if (!last) {
      errs.push('没有带 meta 的卡片，无法核对组数展开（接口需返回 card_items_meta）');
    } else {
      let want = 0;
      for (const it of last.card_items_meta) {
        const meta = (it && it.meta) || {};
        let n = Number(meta.sets);
        if (!Number.isFinite(n)) n = 3; // 与 session_service._sets_for_item 的缺省一致
        want += Math.max(1, Math.min(n, 12));
      }
      if (Number(a.set_count) !== want) {
        errs.push(`落库组数 ${a.set_count} ≠ 按卡片展开 ${want}`);
      }
    }
  }

  const got = a.exercises || [];
  if (c.exercises_exact) {
    const miss = c.exercises_exact.filter((x) => !got.includes(x));
    const extra = got.filter((x) => !c.exercises_exact.includes(x));
    if (miss.length) errs.push(`缺动作：${miss.join(',')}`);
    if (extra.length) errs.push(`多动作：${extra.join(',')}`);
  }
  if (c.exercises_has) {
    const miss = c.exercises_has.filter((x) => !got.some((g) => String(g).includes(x)));
    if (miss.length) errs.push(`缺动作：${miss.join(',')}`);
  }
  // 改稿里被删掉的动作必须真的不在落库结果里（exercises_has: [] 是空操作，别再用它表意）
  if (c.exercises_none) {
    const hit = c.exercises_none.filter((x) => got.some((g) => String(g).includes(x)));
    if (hit.length) errs.push(`不该落库却落库了：${hit.join(',')}`);
  }
  if (c.exercises_min !== undefined && got.length < c.exercises_min) {
    errs.push(`动作数 ${got.length} < ${c.exercises_min}`);
  }
  if (c.exercises_max !== undefined && got.length > c.exercises_max) {
    errs.push(`动作数 ${got.length} > ${c.exercises_max}`);
  }

  return { pass: errs.length === 0, score: errs.length ? 0 : 1, reason: errs.join('; ') };
};
