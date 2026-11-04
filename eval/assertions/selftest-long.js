// 长对话断言自测：node eval/assertions/selftest-long.js
// 覆盖 thread.js / adopt.js / shape-long.js —— 这三个文件是靠假 metadata 判定对错的，
// 改了断言必须跑这个，否则很容易写出「怎么都不会红」的空断言（v1 的 L08/L13 就是）。
const path = require('path');
const thread = require(path.join(__dirname, 'thread.js'));
const adopt = require(path.join(__dirname, 'adopt.js'));
const shape = require(path.join(__dirname, 'shape-long.js'));

const ctx = (metadata, config) => ({ metadata, config: config || {} });
const runThread = (m, c) => {
  const r = thread('answer', ctx(m, c));
  return { pass: r.pass, reason: r.reason };
};
const runAdopt = (m, c) => {
  const r = adopt('answer', ctx(m, c));
  return { pass: r.pass, reason: r.reason };
};
const runShape = (m) => {
  const r = shape('answer', ctx(m));
  return { pass: r.pass, reason: r.reason };
};

const ITEMS = ['哑铃卧推', '上斜哑铃卧推', '龙门架夹胸'];
// sets 可以是数字或数组；元数据条数始终跟着条目走，别让 selftest 自己造出长度不一致的数据
const metaFor = (items, sets) =>
  items.map((title, i) => ({
    title,
    selected: true,
    meta: { sets: Array.isArray(sets) ? sets[i] : sets },
  }));
const META = (sets) => metaFor(ITEMS, sets);

// 造一轮：条目数与 selected 自动跟着 items 走
const T = (over) => {
  const o = over || {};
  const items = o.card_items || ITEMS;
  const meta = o.card_items_meta || META(3);
  return {
    index: 0,
    route: 'plan',
    topic: 'plan',
    draft_relation: null,
    session_target: null,
    card_title: '胸训',
    card_items: items,
    card_items_meta: meta,
    card_item_count: items.length,
    selected_count: items.length,
    dropped: [],
    text_block: '排好了',
    ...o,
  };
};
const M = (turns, adopted) => ({ turns, adopted: adopted || null });

const CHEST = T({});
const REVISED_ITEMS = ['哑铃卧推', '上斜哑铃卧推'];
const CHEST_REVISED = T({ card_items: REVISED_ITEMS, card_items_meta: metaFor(REVISED_ITEMS, [4, 3]) });
const CHEST_NEW = T({ card_title: '背训', card_items: ['高位下拉'], card_items_meta: metaFor(['高位下拉'], 3) });
const CHAT = T({ route: 'chat', card_title: null, card_items: [], card_items_meta: [], card_item_count: 0, selected_count: 0 });

const checks = [];
const expect = (name, got, want) => checks.push({ name, got: got.pass, want, reason: got.reason });

// ---------- thread.js：卡片有无 / 标题 ----------
expect('thread 第一轮出卡', runThread(M([CHEST]), { turn: 1, route: 'plan', card: 'exists', min_items: 3 }), true);
expect('thread 该出卡却没卡', runThread(M([CHAT]), { turn: 1, card: 'exists' }), false);
expect('thread 不该出卡却出了', runThread(M([CHEST]), { card: 'none' }), false);
expect('thread 改稿保留标题', runThread(M([CHEST, CHEST_REVISED]), { turn: 2, keeps_title: true }), true);
expect('thread 改稿被当成新开课', runThread(M([CHEST, CHEST_NEW]), { turn: 2, keeps_title: true }), false);
expect('thread 没上一张卡不能断言标题不变', runThread(M([CHAT, CHEST]), { turn: 2, keeps_title: true }), false);
expect('thread 换部位标题变了', runThread(M([CHEST, CHEST_NEW]), { turn: 2, changed_title: true }), true);
expect('thread 该换部位却还是旧标题', runThread(M([CHEST, CHEST_REVISED]), { turn: 2, changed_title: true }), false);
expect('thread 没卡片时 changed_title 不能空过', runThread(M([CHEST, CHAT]), { turn: 2, changed_title: true }), false);

// ---------- thread.js：条目名单 / 跨轮比较 ----------
expect('thread 条目数下限', runThread(M([CHEST_REVISED]), { turn: 1, min_items: 3 }), false);
expect('thread 条目数上限', runThread(M([CHEST]), { turn: 1, max_items: 2 }), false);
expect('thread 不该出现龙门架', runThread(M([CHEST]), { turn: 1, items_not_has: ['龙门架'] }), false);
expect('thread 换成上斜', runThread(M([CHEST]), { turn: 1, items_has: ['上斜'] }), true);
expect('thread 删一项数变少', runThread(M([CHEST, CHEST_REVISED]), { turn: 2, fewer_items_than_prev: true }), true);
expect('thread 说删却没删', runThread(M([CHEST, T({})]), { turn: 2, fewer_items_than_prev: true }), false);
expect('thread 第一个动作没被动', runThread(M([CHEST, CHEST_REVISED]), { turn: 2, same_first_item: true }), true);
expect('thread 第一个动作被动了', runThread(M([CHEST, T({ card_items: ['上斜哑铃卧推', '龙门架夹胸'], card_items_meta: metaFor(['上斜哑铃卧推', '龙门架夹胸'], 3) })]), { turn: 2, same_first_item: true }), false);
expect('thread 没有上一轮不能比较条目数', runThread(M([CHEST]), { turn: 1, fewer_items_than_prev: true }), false);

// ---------- thread.js：组数（需要 card_items_meta） ----------
expect('thread 组数都改成 4', runThread(M([T({ card_items_meta: META(4) })]), { turn: 1, sets_all: 4 }), true);
expect('thread 组数没都改成 4', runThread(M([T({ card_items_meta: META([4, 4, 3]) })]), { turn: 1, sets_all: 4 }), false);
expect('thread 组数下限', runThread(M([T({ card_items_meta: META([4, 2, 3]) })]), { turn: 1, sets_min: 3 }), false);
expect('thread 没 meta 不能空过组数断言', runThread(M([T({ card_items_meta: [] })]), { turn: 1, sets_all: 4 }), false);

// ---------- thread.js：伤痛 / 文案 / 轮次 ----------
expect('thread 伤痛 drop 命中', runThread(M([T({ card_items: ['腿举'], card_items_meta: metaFor(['腿举'], 3), dropped: ['杠铃硬拉'] })]), { turn: 1, drops_any: ['硬拉'] }), true);
expect('thread 伤痛 drop 没命中', runThread(M([T({ dropped: [] })]), { turn: 1, drops_any: ['硬拉'] }), false);
expect('thread 文案不该出现', runThread(M([CHEST]), { turn: 1, text_not_has: ['排好了'] }), false);
expect('thread route 多选', runThread(M([T({ route: 'clarify', card_title: null, card_items: [], card_items_meta: [], card_item_count: 0, selected_count: 0 })]), { turn: 1, route: ['plan', 'clarify'] }), true);
expect('thread 轮次越界', runThread(M([CHEST]), { turn: 3 }), false);
expect('thread 没有轮次结果', runThread({ turns: [] }, { turn: 1 }), false);

// ---------- adopt.js ----------
const ADOPTED = {
  status: 'active',
  set_count: 9,
  exercises: ['上斜哑铃卧推', '哑铃卧推', '龙门架夹胸'],
};
expect('adopt 状态 + 组数', runAdopt(M([CHEST], ADOPTED), { status: 'active', set_count_min: 9 }), true);
expect('adopt 状态不符', runAdopt(M([CHEST], { ...ADOPTED, status: 'done' }), { status: 'active' }), false);
expect('adopt 组数与卡片展开一致', runAdopt(M([CHEST], ADOPTED), { set_count_matches_last_card: true }), true);
expect('adopt 组数没按 meta.sets 展开', runAdopt(M([CHEST], { ...ADOPTED, set_count: 10 }), { set_count_matches_last_card: true }), false);
expect('adopt 删掉的动作不该落库', runAdopt(M([CHEST], ADOPTED), { exercises_none: ['引体'] }), true);
expect('adopt 删掉的动作还在库里', runAdopt(M([CHEST], { ...ADOPTED, exercises: ['引体向上', '高位下拉'] }), { exercises_none: ['引体'] }), false);
expect('adopt 动作数下限', runAdopt(M([CHEST], { ...ADOPTED, exercises: ['哑铃卧推'] }), { exercises_min: 2 }), false);
expect('adopt 没有 adopted', runAdopt(M([CHEST], null), { status: 'active' }), false);

// ---------- shape-long.js ----------
expect('shape 正常', runShape(M([CHEST, CHAT])), true);
expect('shape 没有轮次', runShape({ turns: [] }), false);
expect('shape route 为空', runShape(M([T({ route: '' })])), false);
expect('shape 条目数对不上', runShape(M([T({ card_item_count: 9 })])), false);
expect('shape 有标题没条目', runShape(M([T({ card_items: [], card_items_meta: [], card_item_count: 0, selected_count: 0 })])), false);
expect('shape meta 条数对不上', runShape(M([T({ card_items_meta: META(3).slice(0, 2) })])), false);

// ---------- 为什么 defaultTest 必须是 file:// ----------
// promptfoo 对内联多行 value 的求值方式是 new Function('output','context','process', body)。
// 整段写成箭头函数时，函数体里只有一个不会被调用的表达式语句 → 永远返回 undefined。
const inlineStyle = new Function(
  'output',
  'context',
  'process',
  '(output, ctx) => { return { pass: true, score: 1, reason: "x" }; }',
);
expect('内联箭头函数返回 undefined（证明必须用 file://）', { pass: inlineStyle('x', {}, {}) === undefined }, true);

let failed = 0;
for (const c of checks) {
  const ok = c.got === c.want;
  if (!ok) failed++;
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${c.name} → pass=${c.got} want=${c.want} ${c.reason ? '[' + c.reason + ']' : ''}`);
}
console.log(`\n${checks.length - failed}/${checks.length} 通过`);
process.exit(failed ? 1 : 0);
