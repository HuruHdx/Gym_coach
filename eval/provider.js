/**
 * promptfoo 自定义 provider（v0.2）：把 /api/eval/qa 的整份 JSON 拆成
 *   output   = answer（contains / llm-rubric 只看这段）
 *   metadata = route / branch / kb / search / citations / intent / model_called / suggestions
 *
 * promptfoo 的 file:// provider 必须是 class（不是函数导出）。
 * 环境变量：EVAL_BASE_URL（默认 http://127.0.0.1:8000）、APP_TOKEN（默认 dev-token）
 */
class GymCoachEvalProvider {
  constructor(options = {}) {
    this.options = options;
    const config = options.config || {};
    this.baseUrl = config.baseUrl || options.baseUrl || process.env.EVAL_BASE_URL || 'http://127.0.0.1:8000';
    this.token = config.token || options.token || process.env.APP_TOKEN || 'dev-token';
    this.mode = config.mode || options.mode || null;
  }

  id() {
    return 'gym-coach-eval';
  }

  async callApi(prompt, context) {
    const vars = (context && context.vars) || {};
    const searchMode = vars.search_mode || 'fixture';

    const body = {
      question: vars.question,
      history: vars.history || [],
      profile: vars.profile || null,
      draft_title: vars.draft_title || null,
      draft_items: vars.draft_items || [],
      search_mode: searchMode,
      search_fixture: vars.search_fixture || [],
    stats_fixture: vars.stats_fixture || [],
    };
    if (vars.thresholds) body.thresholds = vars.thresholds;
    const mode = vars.mode || this.mode;
    if (mode) body.mode = mode;

    const res = await fetch(`${this.baseUrl}/api/eval/qa`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', Authorization: `Bearer ${this.token}`},
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      // 让 promptfoo 记成 provider error，而不是「回答不合格」
      return {error: `POST /api/eval/qa ${res.status}: ${(await res.text()).slice(0, 300)}`};
    }
    const data = await res.json();
    const intent = data.intent || {};
    // 意图评测不生成回答，表格里的 output 空着就只剩 PASS。把分类写出来。
    const output =
      mode === 'intent'
        ? `topic=${intent.topic || '-'}  domain=${intent.domain || '-'}  route=${data.route || '-'}`
        : data.answer;

    return {
      output,
      metadata: {
        route: data.route,
        branch: data.branch,
        kb: data.kb,
        search: data.search,
        citations: data.citations,
        intent: data.intent,
        // v0.2 契约字段：谁写的回答、反问选项
        model_called: data.model_called,
        suggestions: data.suggestions,
        stats: data.stats || {queried: false, filter: {}, tool_calls: [], hits: []},
        // 非契约字段，只给断言区分「该不该搜」
        search_mode: searchMode,
        question: vars.question,
      },
    };
  }
}

module.exports = GymCoachEvalProvider;
