/**
 * 契约形状断言（v0.3）：每个 case 都跑。
 * v0.3 相对 v0.2：新增 branch=rule、sources 字段；kb 的「练哪里」允许调模型。
 *
 * 依据：评测架构需求.md §3.5 + §5.3，实施方案 §5。
 */
// 过渡期：后端闲聊当前发 branch="llm"（graph.py），旧值 "chitchat" 保留兼容。
// 契约（评测架构需求 §5.3）在这两个值里二选一后，删掉另一个。
const BRANCHES = ['kb', 'knowledge', 'compare', 'ask', 'rule', 'search', 'memory', 'adopt', 'chitchat', 'llm', 'plan', 'clarify', 'nutrition'];
const ROUTED = ['plan', 'clarify', 'nutrition']; // 不查库、不搜、不调模型
const NO_MODEL = ['ask', 'adopt', 'memory', 'plan', 'clarify', 'nutrition'];

module.exports = (output, context) => {
  const m = (context && context.metadata) || {};
  const kb = m.kb || {};
  const search = m.search || {};
  const errs = [];
  const push = (x) => errs.push(x);

  if (!['clarify', 'plan', 'chat', 'nutrition'].includes(m.route)) push(`route=${m.route}`);
  if (!BRANCHES.includes(m.branch)) push(`branch=${m.branch}`);
  if (typeof kb.queried !== 'boolean') push('kb.queried');
  if (typeof kb.hit !== 'boolean') push('kb.hit');
  if (typeof search.called !== 'boolean') push('search.called');
  if (typeof m.model_called !== 'boolean') push('model_called');
  if (!Array.isArray(m.citations)) push('citations');
  if (!Array.isArray(m.suggestions)) push('suggestions');
  if (typeof output !== 'string' || !output.trim()) push('answer_empty');

  const branch = m.branch;
  const hits = Array.isArray(kb.hits) ? kb.hits : [];
  const cited = (m.citations || []).map(String);
  const hitIds = hits.map((h) => String(h.id));
  const opts = m.suggestions || [];
  const sources = m.sources;

  // citations：只有 kb 允许非空；kb 的引用必须来自本次命中，且第 1 条就是引用源
  if (branch !== 'kb' && cited.length) push(`citations_on_${branch}`);
  for (const c of m.citations || []) {
    if (typeof c !== 'string') push(`citation_type=${typeof c}`);
    else if (branch === 'kb' && !hitIds.includes(c)) push(`citation_not_in_hits=${c}`);
  }
  if (branch === 'kb') {
    if (!hits.length) push('kb_without_hits');
    if (cited.length && hitIds.length && cited[0] !== hitIds[0]) push('citation_not_top1');
    for (const h of hits.slice(0, 1)) {
      if (typeof h.target !== 'string' || !h.target) push('hit_target_missing');
    }
  }

  // suggestions：只有 ask 有；其它分支必须是空数组
  if (branch !== 'ask' && opts.length) push(`suggestions_on_${branch}`);
  if (branch === 'ask') {
    if (m.route !== 'chat') push(`ask_route=${m.route}`);
    if (opts.length < 2) push(`ask_options=${opts.length}`);
    if (opts.length > 5) push(`ask_options=${opts.length}>5`);
    const labels = opts.map((s) => String((s && s.label) || ''));
    if (!labels.some((l) => l.includes('都不是'))) push('ask_missing_none_of_above');
    for (const s of opts) {
      if (!s || !s.label || !s.prompt) push('ask_option_shape');
    }
  }

  // sources（v0.3，可选）：给了就必须是合法形状
  if (sources !== undefined && sources !== null) {
    if (!Array.isArray(sources)) push('sources_not_array');
    else {
      for (const s of sources) {
        if (!['kb', 'rule', 'web'].includes((s && s.type) || '')) push(`source_type=${(s && s.type)}`);
        if (typeof (s && s.ref) !== 'string' || !s.ref) push('source_ref_missing');
      }
    }
  }

  // 搜索：kb / knowledge / compare / ask / rule 一律不搜；search 必须搜（off 模式除外）
  if (['kb', 'knowledge', 'compare', 'ask', 'rule', 'chitchat', 'llm'].includes(branch) && search.called) {
    push(`search_called_on_${branch}`);
  }
  if (branch === 'search' && !search.called && m.search_mode !== 'off') push('search_branch_not_called');

  // 查库：路由分支和 memory/adopt 都不查
  if ([...ROUTED, 'memory', 'adopt'].includes(branch) && kb.queried) push(`kb_queried_on_${branch}`);
  if (['kb', 'knowledge', 'compare', 'ask', 'search'].includes(branch) && !kb.queried) {
    push(`kb_not_queried_on_${branch}`);
  }
  // rule 允许查库（拿替代动作），也允许不查（纯规则）

  // model_called 与 3.5 的「谁来写回答」一致
  if (NO_MODEL.includes(branch) && m.model_called) push(`model_called_on_${branch}`);
  if (['knowledge', 'compare', 'rule'].includes(branch) && !m.model_called) push(`model_skipped_on_${branch}`);
  if (branch === 'search') {
    const hasResults = (search.results || []).length > 0;
    // 有结果却不调模型写回答 = 浪费搜索，保留护栏
    if (hasResults && !m.model_called) push('search_has_results_but_model_skipped');
    // 无结果时按教练知识答是设计预期（knowledge_reply.py 兜底），不再误报
  }

  return {pass: errs.length === 0, score: errs.length ? 0 : 1, reason: errs.join('; ')};
};
