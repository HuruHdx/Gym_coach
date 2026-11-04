/**
 * 长对话的基础形状检查（promptfooconfig-long.yaml 的 defaultTest）。
 *
 * 为什么必须是一个文件，而不是写在 YAML 里：
 * promptfoo 对内联 javascript 断言的处理是
 *     new Function('output', 'context', 'process', functionBody)
 * 多行 value 会被**整段当函数体**执行。于是 YAML 里写
 *     value: |
 *       (output, ctx) => { ... }
 * 只是一个不会被调用的箭头函数表达式语句，返回 undefined，断言必然报
 * "Custom function must return a boolean ... Got type undefined" —— 18 条用例全 ERROR。
 * 内联写法只适合单行表达式或裸露的函数体（自带 return）。
 *
 * 这里检查的是「接口形状自洽」，不判断行为对错（行为断言在 thread.js / adopt.js）：
 *   - 有轮次，每轮有 route
 *   - card_items 与 card_item_count 一致，selected_count 不超过条目数
 *   - 有卡片标题就必须有条目，反之亦然
 *   - card_items_meta 与卡片条目数一致（老接口没这个字段时跳过）
 */
module.exports = (output, context) => {
  const m = (context && context.metadata) || {};
  const turns = m.turns || [];
  if (!turns.length) {
    return { pass: false, score: 0, reason: 'metadata.turns 为空（接口没返回轮次）' };
  }

  const bad = [];
  turns.forEach((t, i) => {
    const tag = `第${i + 1}轮`;
    if (!t.route) bad.push(`${tag} route 为空`);

    const items = Array.isArray(t.card_items) ? t.card_items : [];
    if (items.length !== (t.card_item_count || 0)) {
      bad.push(`${tag} card_items(${items.length}) ≠ card_item_count(${t.card_item_count})`);
    }
    if ((t.selected_count || 0) > (t.card_item_count || 0)) {
      bad.push(`${tag} selected(${t.selected_count}) > items(${t.card_item_count})`);
    }
    if (t.card_title && !(t.card_item_count > 0)) {
      bad.push(`${tag} 有标题却没有条目：${t.card_title}`);
    }
    if (!t.card_title && t.card_item_count > 0) {
      bad.push(`${tag} 有条目却没有标题`);
    }

    const metas = t.card_items_meta;
    if (Array.isArray(metas) && metas.length && metas.length !== t.card_item_count) {
      bad.push(`${tag} card_items_meta(${metas.length}) ≠ 卡片条目(${t.card_item_count})`);
    }
  });

  return { pass: bad.length === 0, score: bad.length ? 0 : 1, reason: bad.join('; ') };
};
