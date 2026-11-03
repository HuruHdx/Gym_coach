// 断言自测（v0.2）：给假 metadata，验证「该红的会红、该绿的会绿」。
//   node eval/assertions/selftest.js
const path = require('path');
const load = (n) => require(path.join(__dirname, n));

const shape = load('shape.js');
const branch = load('branch.js');
const cites = load('cites.js');
const text = load('text.js');
const intent = load('intent.js');

// 契约 v0.2：hits 带 target；kb 的「练哪里」不调模型
const kbMeta = {
  route: 'chat',
  branch: 'kb',
  kb: {queried: true, hit: true, top_score: 1, margin: 1, reason: 'exact_name',
       hits: [{id: '1350', name: '杠杆坐姿划船', score: 1, target: '上背', snippet: '目标肌：上背（upper back）'}],
       near_miss: []},
  search: {called: false, query: null, results: []},
  citations: ['1350'],
  intent: {agent: 'coach_chat', muscles: ['背'], focus_exercises: ['杠杆坐姿划船'], rewrite: '询问杠杆坐姿划船的目标肌'},
  model_called: false,
  suggestions: [],
};

const kbHowTo = {...kbMeta, kb: {...kbMeta.kb, reason: 'exact_name'}, model_called: true};

const knowledgeMeta = {
  route: 'chat', branch: 'knowledge',
  kb: {queried: true, hit: false, top_score: 0.81, margin: 0.02, reason: 'family', hits: [], near_miss: []},
  search: {called: false, query: null, results: []},
  citations: [], intent: {agent: 'coach_chat', muscles: ['背'], focus_exercises: [], rewrite: '一类动作'},
  model_called: true, suggestions: [],
};

const askMeta = {
  route: 'chat', branch: 'ask',
  kb: {queried: true, hit: false, top_score: 0.62, margin: 0.03, reason: 'ambiguous', hits: [],
       near_miss: [{id: '1350', name: '杠杆坐姿划船', score: 0.62}]},
  search: {called: false, query: null, results: []},
  citations: [], intent: {agent: 'coach_chat', muscles: [], focus_exercises: [], rewrite: '悍马划船'},
  model_called: false,
  suggestions: [{label: '杠杆坐姿划船', prompt: '杠杆坐姿划船练哪里'}, {label: '都不是', prompt: '都不是'}],
};

const searchMeta = {
  route: 'chat', branch: 'search',
  kb: {queried: true, hit: false, top_score: 0.2, margin: 0.1, reason: 'below_miss', hits: [], near_miss: []},
  search: {called: true, query: '新手一周练几次背', results: [{title: 't', url: 'u', snippet: 's'}]},
  citations: [], intent: {agent: 'coach_chat', muscles: [], focus_exercises: [], rewrite: '频率'},
  model_called: true, suggestions: [],
};

const adoptMeta = {
  route: 'chat', branch: 'adopt',
  kb: {queried: false, hit: false, top_score: 0, margin: 0, reason: 'not_queried', hits: [], near_miss: []},
  search: {called: false, query: null, results: []},
  citations: [], intent: {agent: 'coach_chat', muscles: [], focus_exercises: [], rewrite: '确认'},
  model_called: false, suggestions: [],
};

const chitchatMeta = {
  route: 'chat', branch: 'llm',
  kb: {queried: false, hit: false, top_score: 0, margin: 0, reason: 'chitchat', hits: [], near_miss: []},
  search: {called: false, query: null, results: []},
  citations: [], intent: {agent: 'coach_chat', muscles: [], focus_exercises: [], rewrite: '闲聊'},
  model_called: true, suggestions: [],
};

const ctx = (metadata, config) => ({metadata, config: config || {}});
const run = (fn, output, metadata, config) => {
  const r = fn(output, ctx(metadata, config));
  return {pass: r.pass, reason: r.reason};
};

const checks = [];
const expect = (name, got, want) => checks.push({name, got: got.pass, want, reason: got.reason});
const withMeta = (base, patch) => ({...base, ...patch});

expect('shape kb 正常', run(shape, '主要练上背。', kbMeta), true);
expect('shape 引用不在 hits', run(shape, 'x', withMeta(kbMeta, {citations: ['9999']})), false);
expect('shape 引用不是 top1', run(shape, 'x', withMeta(kbMeta, {
  citations: ['2265'], kb: {...kbMeta.kb, hits: [...kbMeta.kb.hits, {id: '2265', target: '上背'}]}})), false);
expect('shape hit 缺 target', run(shape, 'x', withMeta(kbMeta, {
  kb: {...kbMeta.kb, hits: [{id: '1350', snippet: '目标肌：上背'}]}})), false);
expect('shape 数字 citation 类型', run(shape, 'x', withMeta(kbMeta, {citations: [1350]})), false);
expect('shape knowledge 正常', run(shape, 'x', knowledgeMeta), true);
expect('shape knowledge 带了引用', run(shape, 'x', withMeta(knowledgeMeta, {citations: ['1350']})), false);
expect('shape knowledge 却没调模型', run(shape, 'x', withMeta(knowledgeMeta, {model_called: false})), false);
expect('shape knowledge 却给了选项', run(shape, 'x', withMeta(knowledgeMeta, {
  suggestions: [{label: '杠杆坐姿划船', prompt: 'x'}]})), false);
expect('shape knowledge 却搜索了', run(shape, 'x', withMeta(knowledgeMeta, {
  search: {called: true, query: 'x', results: []}})), false);
expect('shape ask 正常', run(shape, 'x', askMeta), true);
expect('shape ask 只有一个选项', run(shape, 'x', withMeta(askMeta, {
  suggestions: [{label: '杠杆坐姿划船', prompt: 'x'}]})), false);
expect('shape ask 缺「都不是」', run(shape, 'x', withMeta(askMeta, {
  suggestions: [{label: '杠杆坐姿划船', prompt: 'x'}, {label: '绳索坐姿划船', prompt: 'y'}]})), false);
expect('shape ask 却调了模型', run(shape, 'x', withMeta(askMeta, {model_called: true})), false);
expect('shape ask 却搜索了', run(shape, 'x', withMeta(askMeta, {
  search: {called: true, query: 'x', results: []}})), false);
expect('shape adopt 正常', run(shape, 'x', adoptMeta), true);
expect('shape adopt 却调了模型', run(shape, 'x', withMeta(adoptMeta, {model_called: true})), false);
expect('shape adopt 却查了库', run(shape, 'x', withMeta(adoptMeta, {kb: {...adoptMeta.kb, queried: true}})), false);
expect('shape 闲聊分支（llm）正常', run(shape, 'x', chitchatMeta), true);
expect('shape 闲聊分支（llm）却搜索了', run(shape, 'x', withMeta(chitchatMeta, {
  search: {called: true, query: 'x', results: []}})), false);
expect('shape search 有结果但没调模型', run(shape, 'x', withMeta(searchMeta, {model_called: false})), false);
// 无结果时按教练知识答是设计预期（knowledge_reply.py 兜底），不是错
expect('shape search 无结果按教练知识答（允许）', run(shape, 'x', withMeta(searchMeta, {
  model_called: true, search: {...searchMeta.search, results: []}})), true);
expect('shape off 模式不搜', run(shape, 'x', withMeta(searchMeta, {
  search_mode: 'off', search: {...searchMeta.search, called: false, results: []}, model_called: false})), true);

expect('branch kb 期望命中', run(branch, 'x', kbMeta, {branch: 'kb', reason: 'exact_name'}), true);
expect('branch 实际 knowledge', run(branch, 'x', knowledgeMeta, {branch: 'kb'}), false);
expect('branch 一类动作', run(branch, 'x', knowledgeMeta,
  {branch: 'knowledge', reason: 'family', model_called: true, suggestions_empty: true}), true);
expect('branch 反问选项', run(branch, 'x', askMeta,
  {branch: 'ask', reason: 'ambiguous', model_called: false, suggestions_min: 2, suggestions_include: ['都不是']}), true);
expect('branch 反问选项缺都不是', run(branch, 'x', askMeta, {suggestions_include: ['都不是啊']}), false);
expect('branch 模型开关', run(branch, 'x', kbHowTo, {model_called: false}), false);
expect('branch 搜索词含悍马', run(branch, 'x',
  withMeta(searchMeta, {search: {...searchMeta.search, query: '悍马划船练哪里'}}),
  {search_query_includes: '悍马划船', search_query_excludes: ['杠杆坐姿划船']}), true);
expect('branch 分数超区间', run(branch, 'x', kbMeta, {top_score_max: 0.8}), false);

expect('cites target 一致', run(cites, '主要练上背，会带到肱二头肌。', kbMeta,
  {exactly_one: true, any_of: ['1350'], target_muscle: true, extra_muscles: ['上背', '背阔肌']}), true);
expect('cites 说成背阔肌', run(cites, '主要练背阔肌。', kbMeta,
  {exactly_one: true, any_of: ['1350'], target_muscle: true, extra_muscles: ['上背', '背阔肌']}), false);
expect('cites 引了两条', run(cites, '上背', withMeta(kbMeta, {citations: ['1350', '2265']}), {exactly_one: true}), false);
expect('cites 该空不空', run(cites, 'x', kbMeta, {empty: true}), false);
expect('cites 无 target 字段退回 snippet', run(cites, '主要练上背。', withMeta(kbMeta, {
  citations: ['0292'], kb: {...kbMeta.kb, hits: [{id: '0292', snippet: '目标肌：上背（upper back）'}]}}),
  {target_muscle: true}), true);

expect('text 禁具体重量', run(text, '上次卧推 70kg，建议从 72.5kg 开始。', {}, {forbid_weight: true}), false);
expect('text 没记录通过', run(text, '档案里没有卧推的历史记录。', {}, {forbid_weight: true}), true);
expect('text 中文占比', run(text, 'Keep your chest up and pull with your elbows.', {},
  {zh_ratio_min: 0.8, english_run_max: 4}), false);
expect('text 露 JSON', run(text, '{"text":"上背"}', {}, {forbid_json: true}), false);
expect('text 称呼老炮', run(text, '老炮，你先加重量。', {}, {not_contains: ['老炮']}), false);
expect('text 字数超限', run(text, '上背'.repeat(60), {}, {max_chars: 100}), false);

expect('intent 焦点为空', run(intent, 'x', kbMeta, {focus_exercises_empty: true}), false);
expect('intent 部位包含', run(intent, 'x', kbMeta, {muscles_include: ['背']}), true);
expect('intent agent 错', run(intent, 'x', kbMeta, {agent: 'coach_plan'}), false);

let failed = 0;
for (const c of checks) {
  const ok = c.got === c.want;
  if (!ok) failed++;
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${c.name} → pass=${c.got} want=${c.want} ${c.reason ? '[' + c.reason + ']' : ''}`);
}
console.log(`\n${checks.length - failed}/${checks.length} 通过`);
process.exit(failed ? 1 : 0);
