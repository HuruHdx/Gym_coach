/**
 * 意图断言（topic + domain）。只看意图，不看检索、不看回答质量。
 *
 * 契约：metadata.intent.topic ∈ plan | qa | chitchat
 *       metadata.intent.domain ∈ training | nutrition | general（可省略断言）
 *
 * config:
 *   topic: "qa"                期望 topic
 *   domain: "nutrition"               期望 domain（只在营养类用例上断言）
 *   route: "chat" | ["plan","clarify"] 期望 route（可省略）
 */
const TOPICS = ['plan', 'qa', 'chitchat'];
const DOMAINS = ['training', 'nutrition', 'general'];

module.exports = (output, context) => {
  const c = (context && context.config) || {};
  const m = (context && context.metadata) || {};
  const intent = m.intent || {};
  const topic = intent.topic;
  const domain = intent.domain;
  const errs = [];

  if (topic === undefined || topic === null || topic === '') {
    errs.push('intent.topic 未返回（契约未落地）');
  } else if (!TOPICS.includes(topic)) {
    errs.push(`topic=${topic} 不在枚举内`);
  } else if (c.topic !== undefined && topic !== c.topic) {
    errs.push(`topic=${topic} want=${c.topic}`);
  }

  if (c.domain !== undefined) {
    if (domain === undefined || domain === null || domain === '') {
      errs.push('intent.domain 未返回');
    } else if (!DOMAINS.includes(domain)) {
      errs.push(`domain=${domain} 不在枚举内`);
    } else if (domain !== c.domain) {
      errs.push(`domain=${domain} want=${c.domain}`);
    }
  }

  if (c.route !== undefined) {
    const routes = Array.isArray(c.route) ? c.route : [c.route];
    if (!routes.includes(m.route)) errs.push(`route=${m.route} ∉ ${routes.join('|')}`);
  }

  return {pass: errs.length === 0, score: errs.length ? 0 : 1, reason: errs.join('; ')};
};
