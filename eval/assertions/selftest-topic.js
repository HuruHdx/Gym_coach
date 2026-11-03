// topic 断言自测（v2）：node eval/assertions/selftest-topic.js
const path = require('path');
const topic = require(path.join(__dirname, 'topic.js'));

const ctx = (metadata, config) => ({metadata, config: config || {}});
const run = (m, c) => {
  const r = topic('answer', ctx(m, c));
  return {pass: r.pass, reason: r.reason};
};
const meta = (t, route, d) => ({intent: {topic: t, domain: d}, route: route || 'chat'});

const checks = [];
const expect = (name, got, want) => checks.push({name, got: got.pass, want, reason: got.reason});

expect('topic qa', run(meta('qa', 'chat', 'training'), {topic: 'qa'}), true);
expect('topic plan', run(meta('plan', 'plan', 'training'), {topic: 'plan'}), true);
expect('topic chitchat', run(meta('chitchat', 'chat', 'general'), {topic: 'chitchat'}), true);
expect('topic 判错', run(meta('plan', 'plan', 'training'), {topic: 'qa'}), false);
expect('topic 未返回', run({intent: {}, route: 'chat'}, {topic: 'plan'}), false);
expect('旧值 memory 不在枚举', run(meta('memory', 'chat', 'training'), {topic: 'qa'}), false);
expect('domain nutrition', run(meta('qa', 'chat', 'nutrition'), {topic: 'qa', domain: 'nutrition'}), true);
expect('domain 判错', run(meta('qa', 'chat', 'training'), {domain: 'nutrition'}), false);
expect('domain 未返回但要求了', run({intent: {topic: 'qa'}, route: 'chat'}, {domain: 'nutrition'}), false);
expect('route 正确', run(meta('plan', 'plan', 'training'), {topic: 'plan', route: 'plan'}), true);
expect('route 多选', run(meta('plan', 'clarify', 'training'), {topic: 'plan', route: ['plan', 'clarify']}), true);
expect('canary 空 config', run(meta('chitchat', 'chat', 'general'), {}), true);

let failed = 0;
for (const c of checks) {
  const ok = c.got === c.want;
  if (!ok) failed++;
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${c.name} → pass=${c.got} want=${c.want} ${c.reason ? '[' + c.reason + ']' : ''}`);
}
console.log(`\n${checks.length - failed}/${checks.length} 通过`);
process.exit(failed ? 1 : 0);
