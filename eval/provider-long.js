/**
 * 长对话评测 provider：一次请求跑完整条对话。
 *
 * 为什么不用 provider.js 循环调用 /api/eval/qa：
 *   /api/eval/qa 每次都新建内存库、无状态，草稿只能靠 YAML 里手工写 history 传递。
 *   但「上一版草稿里到底有几个动作、哪几个被 drop 了」只有模型自己知道，
 *   手工维护必然和真实链路脱节。所以改由 /api/eval/thread 在同一个库里顺序跑，
 *   自己把上一轮产出的 card 变成下一轮的 draft_items。
 *
 * 输出给 promptfoo 的 output 是整条对话的可读摘要，
 * metadata 里放结构化结果（每轮的 route / topic / 卡片 / 是否被裁）。
 *
 * 环境变量：EVAL_BASE_URL（默认 http://127.0.0.1:8000）、APP_TOKEN（默认 dev-token）
 */
class GymCoachThreadProvider {
  constructor(options = {}) {
    this.options = options;
    const config = options.config || {};
    this.baseUrl =
      config.baseUrl || options.baseUrl || process.env.EVAL_BASE_URL || 'http://127.0.0.1:8000';
    this.token = config.token || options.token || process.env.APP_TOKEN || 'dev-token';
  }

  id() {
    return 'gym-coach-thread';
  }

  async callApi(prompt, context) {
    const vars = (context && context.vars) || {};
    const turns = vars.turns || [];
    if (!turns.length) {
      return { error: '用例缺少 turns' };
    }

    const body = {
      name: vars.name || '',
      turns: turns.map((t) => (typeof t === 'string' ? { text: t } : t)),
      profile: vars.profile || null,
      search_mode: vars.search_mode || 'fixture',
      search_fixture: vars.search_fixture || [],
      stats_fixture: vars.stats_fixture || [],
    };
    if (vars.adopt_after !== undefined) body.adopt_after = vars.adopt_after;
    // 只跑意图、不跑排课（不出卡）。默认 false：长对话必须走真实链路
    if (vars.short_circuit !== undefined) body.short_circuit = Boolean(vars.short_circuit);

    const res = await fetch(`${this.baseUrl}/api/eval/thread`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.token}`,
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      return { error: `POST /api/eval/thread ${res.status}: ${(await res.text()).slice(0, 300)}` };
    }

    const data = await res.json();
    if (data.error) {
      return { error: data.error };
    }

    // 可读摘要：命令行里能直接看出每一轮发生了什么
    const lines = (data.turns || []).map((t) => {
      const sets = (t.card_items_meta || [])
        .map((it) => (it.meta && it.meta.sets !== undefined ? it.meta.sets : '-'))
        .join(',');
      const card = t.card_title
        ? ` card=${t.card_title}(${t.card_item_count}项/选${t.selected_count}${sets ? ` sets=${sets}` : ''})`
        : ' card=-';
      const drop = t.dropped && t.dropped.length ? ` dropped=${t.dropped.join('+')}` : '';
      return `[${t.index + 1}] "${t.text}" → route=${t.route} topic=${t.topic || '-'}${card}${drop}`;
    });
    if (data.adopted) {
      lines.push(
        `[adopt] session=${data.adopted.session_id} status=${data.adopted.status} ` +
          `sets=${data.adopted.set_count} ex=${data.adopted.exercises.join('/')}`,
      );
    }

    return {
      output: lines.join('\n'),
      metadata: {
        turns: data.turns || [],
        adopted: data.adopted || null,
      },
    };
  }
}

module.exports = GymCoachThreadProvider;
