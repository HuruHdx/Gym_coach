/**
 * 会话级断言：看某一轮发生了什么。
 *
 * promptfoo 的断言默认只看「整条 output」，但长对话要看的是「第 3 轮有没有正确改稿」。
 * 所以这里从 metadata.turns 里按序号取那一轮，再做判定。
 *
 * config：
 *   turn         第几轮（从 1 开始）。省略 = 最后一轮
 *   route        期望 route（字符串或数组）
 *   topic        期望 topic
 *   draft_relation  期望的草稿关系（confirm / revise / fresh），不传不断言
 *   session_target  期望的 session_target（keep / switch / ask）
 *   card          "exists" | "none"
 *   keeps_title  该轮卡片标题应等于上一轮标题（改稿不该改标题）
 *   changed_title 该轮卡片标题应不同于上一轮（新开一堂课）
 *   min_items / max_items  卡片条目数范围
 *   items_has / items_not_has  卡片动作名单必须含 / 必须不含（子串匹配）
 *   fewer_items_than_prev  条目数必须比上一轮少（「删掉一项」）
 *   same_first_item        第一个动作必须和上一轮相同（「把第二个换掉」不该动第一个）
 *   sets_all / sets_min / sets_max  卡片 meta.sets（需要接口返回 card_items_meta）
 *   all_selected 卡片里的动作是否全部 selected
 *   drops_any    卡片 meta.dropped 至少含一个指定动作（伤痛规避）
 *   drops_none   卡片 meta.dropped 不含这些动作
 *   text_has / text_not_has  文案包含 / 不含
 */
module.exports = (output, context) => {
  const c = (context && context.config) || {};
  const m = (context && context.metadata) || {};
  const turns = m.turns || [];

  if (!turns.length) {
    return { pass: false, score: 0, reason: 'metadata.turns 为空（接口没返回轮次）' };
  }

  const idx = c.turn ? Number(c.turn) - 1 : turns.length - 1;
  const t = turns[idx];
  if (!t) {
    return { pass: false, score: 0, reason: `没有第 ${idx + 1} 轮（共 ${turns.length} 轮）` };
  }

  const errs = [];
  const tag = `第${idx + 1}轮`;
  const prev = turns[idx - 1];
  const items = Array.isArray(t.card_items) ? t.card_items : [];

  if (c.route !== undefined) {
    const want = Array.isArray(c.route) ? c.route : [c.route];
    if (!want.includes(t.route)) errs.push(`${tag} route=${t.route} ∉ ${want.join('|')}`);
  }
  if (c.topic !== undefined && t.topic !== c.topic) {
    errs.push(`${tag} topic=${t.topic} want=${c.topic}`);
  }
  if (c.draft_relation !== undefined && t.draft_relation !== c.draft_relation) {
    errs.push(`${tag} draft_relation=${t.draft_relation} want=${c.draft_relation}`);
  }
  if (c.session_target !== undefined && t.session_target !== c.session_target) {
    errs.push(`${tag} session_target=${t.session_target} want=${c.session_target}`);
  }

  if (c.card === 'exists' && !t.card_title) {
    errs.push(`${tag} 应该有卡片，实际没有`);
  }
  if (c.card === 'none' && t.card_title) {
    errs.push(`${tag} 不该出卡片，实际出了 ${t.card_title}`);
  }

  // 改稿不能换标题：这是最常见的退化（改一项变成整堂重排）
  if (c.keeps_title) {
    if (!prev || !prev.card_title) {
      errs.push(`${tag} 之前没有卡片，无法断言「标题不变」`);
    } else if (t.card_title !== prev.card_title) {
      errs.push(`${tag} 标题被改了：${prev.card_title} → ${t.card_title}`);
    }
  }
  // 没卡片时「换了标题」无从谈起，不能空过
  if (c.changed_title) {
    if (!prev || !prev.card_title || !t.card_title) {
      errs.push(`${tag} 前后任一轮没有卡片，无法断言「标题变了」`);
    } else if (t.card_title === prev.card_title) {
      errs.push(`${tag} 换了新课时，标题仍是 ${t.card_title}`);
    }
  }

  if (c.min_items !== undefined && t.card_item_count < c.min_items) {
    errs.push(`${tag} 卡片只有 ${t.card_item_count} 项，少于 ${c.min_items}`);
  }
  if (c.max_items !== undefined && t.card_item_count > c.max_items) {
    errs.push(`${tag} 卡片有 ${t.card_item_count} 项，多于 ${c.max_items}`);
  }
  if (c.all_selected) {
    const un = t.card_item_count - t.selected_count;
    if (un > 0) errs.push(`${tag} 有 ${un} 项没被选中`);
  }

  // 按名字看条目：伤痛规避 / 换器械 / 换动作都靠这两个，不要用文案里碰巧出现的字符串
  if (c.items_has) {
    const miss = c.items_has.filter((name) => !items.some((it) => String(it).includes(name)));
    if (miss.length) errs.push(`${tag} 卡片缺动作：${miss.join('|')}（实际 ${items.join('/')}）`);
  }
  if (c.items_not_has) {
    const hit = c.items_not_has.filter((name) => items.some((it) => String(it).includes(name)));
    if (hit.length) errs.push(`${tag} 卡片不该出现：${hit.join('|')}（实际 ${items.join('/')}）`);
  }

  // 跨轮比较：接口按顺序返回条目，所以「删掉一项」「把第二个换掉」都能验
  if (c.fewer_items_than_prev) {
    if (!prev || !prev.card_item_count) {
      errs.push(`${tag} 上一轮没有卡片，无法比较条目数`);
    } else if (!(t.card_item_count < prev.card_item_count)) {
      errs.push(`${tag} 条目数没变少：${prev.card_item_count} → ${t.card_item_count}`);
    }
  }
  if (c.same_first_item) {
    const prevFirst = prev && prev.card_items && prev.card_items[0];
    if (!prevFirst) {
      errs.push(`${tag} 上一轮没有卡片，无法比较第一个动作`);
    } else if (items[0] !== prevFirst) {
      errs.push(`${tag} 第一个动作被动了：${prevFirst} → ${items[0] || '无'}`);
    }
  }

  // 组次改稿（「组数都改成 4 组」）：只有接口带回 card_items_meta 才测得到
  const metas = Array.isArray(t.card_items_meta) ? t.card_items_meta : [];
  const setsOf = () =>
    metas
      .map((it) => {
        const meta = (it && it.meta) || {};
        return meta.sets === undefined || meta.sets === null ? null : Number(meta.sets);
      })
      .filter((n) => n !== null);
  if (c.sets_all !== undefined || c.sets_min !== undefined || c.sets_max !== undefined) {
    if (!metas.length) {
      errs.push(`${tag} 没有 card_items_meta，无法断言组数（接口未返回该字段）`);
    } else {
      const sets = setsOf();
      if (c.sets_all !== undefined) {
        const bad = metas.filter((it) => {
          const meta = (it && it.meta) || {};
          return Number(meta.sets) !== Number(c.sets_all);
        });
        if (bad.length) {
          errs.push(
            `${tag} 组数没都改成 ${c.sets_all}：` +
              bad.map((it) => `${it.title || '?'}=${(it.meta || {}).sets}`).join(','),
          );
        }
      }
      if (c.sets_min !== undefined && sets.some((n) => n < c.sets_min)) {
        errs.push(`${tag} 有动作不到 ${c.sets_min} 组：${sets.join('/')}`);
      }
      if (c.sets_max !== undefined && sets.some((n) => n > c.sets_max)) {
        errs.push(`${tag} 有动作超过 ${c.sets_max} 组：${sets.join('/')}`);
      }
    }
  }

  const dropped = t.dropped || [];
  if (c.drops_any) {
    const hit = c.drops_any.some((name) => dropped.some((d) => String(d).includes(name)));
    if (!hit) errs.push(`${tag} dropped=[${dropped.join(',')}] 未包含 ${c.drops_any.join('|')}`);
  }
  if (c.drops_none) {
    const hit = c.drops_none.filter((name) => dropped.some((d) => String(d).includes(name)));
    if (hit.length) errs.push(`${tag} 不该 drop 却 drop 了：${hit.join(',')}`);
  }

  const text = t.text_block || '';
  if (c.text_has) {
    const miss = c.text_has.filter((s) => !String(text).includes(s));
    if (miss.length) errs.push(`${tag} 文案缺：${miss.join('|')}`);
  }
  if (c.text_not_has) {
    const hit = c.text_not_has.filter((s) => String(text).includes(s));
    if (hit.length) errs.push(`${tag} 文案不该出现：${hit.join('|')}`);
  }

  return { pass: errs.length === 0, score: errs.length ? 0 : 1, reason: errs.join('; ') };
};
