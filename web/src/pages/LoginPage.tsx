import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, markAuthed, setToken } from "../lib/api";
import { MOTTO } from "../lib/brand";

type Props = { onDone: () => void };

/**
 * 登录页（品牌页）。
 *
 * 与日常界面不同的一套视觉：深色 + 荧光黄绿 + 配重片同心圆。
 * 颜色只在 index.css 的 .login-brand 作用域内定义，不改全站主题。
 *
 * 关于认证：现在仍是「单一访问口令」，调 GET /api/auth/verify。
 * 后续接账号体系时，只需要替换 submitCredential 的实现，界面与状态不用动。
 */
export function LoginPage({ onDone }: Props) {
  const [pass, setPass] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  /** 每次失败递增，用来重放抖动动画（同值不会重新触发 CSS animation）。 */
  const [attempt, setAttempt] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (err) inputRef.current?.focus();
  }, [err]);

  /** 唯一需要替换的地方：接账号体系时改这里。 */
  async function submitCredential(secret: string) {
    setToken(secret);
    await api("/api/auth/verify");
    markAuthed();
  }

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    if (busy) return;
    const secret = pass.trim();
    if (!secret) {
      setErr("先输口令");
      setAttempt((n) => n + 1);
      return;
    }
    setBusy(true);
    setErr("");
    try {
      await submitCredential(secret);
      onDone();
    } catch {
      setErr("口令不对。它对应服务器 .env 里的 APP_TOKEN。");
      setAttempt((n) => n + 1);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-brand mx-auto flex h-dvh max-w-md flex-col">
      <div className="lb-sky" aria-hidden />
      <div className="lb-plate" aria-hidden />

      <div className="lb-wrap flex-1">
        {/* ---- 顶部 ---- */}
        <header className="flex shrink-0 items-center justify-between pt-9">
          <span className="flex items-center gap-1.5 text-[9.5px] font-semibold uppercase tracking-[0.2em] text-[var(--lb-ink-2)]">
            <i
              className={`h-[5px] w-[5px] rounded-full ${
                err ? "bg-[var(--lb-danger)]" : "bg-[var(--lb-accent)]"
              }`}
              style={{
                boxShadow: err
                  ? "0 0 9px rgba(255,107,107,.9)"
                  : "0 0 9px rgba(212,255,63,.9)",
              }}
              aria-hidden
            />
            Gym Coach
          </span>
          <span className="text-[9.5px] tracking-[0.14em] text-[var(--lb-ink-3)]">中文</span>
        </header>

        {/* ---- 标题区 ---- */}
        <div className="mt-11">
          <p
            className={`text-[9.5px] font-semibold uppercase tracking-[0.26em] ${
              err ? "text-[var(--lb-danger)]" : "text-[var(--lb-accent)]"
            }`}
          >
            {err ? "Access Denied" : "Personal Training Log"}
          </p>
          <h1 className="mt-3 font-display text-[46px] font-bold italic leading-[0.96] tracking-[-0.045em]">
            先登录
            <br />
            再开练
            <span className="not-italic">.</span>
          </h1>
          <p className="mt-4 font-display text-[17px] font-medium tracking-[-0.01em] text-[var(--lb-ink-2)]">
            赶紧训练吧彦祖
          </p>

          {/* 三栏：不涉及任何用户数据，所有人看到的一样 */}
          <div className="mt-5 flex items-stretch border-y border-[var(--lb-line)]">
            {[
              { cn: "训练", en: "TRAIN" },
              { cn: "记录", en: "LOG" },
              { cn: "渐进", en: "PROGRESS" },
            ].map((item, i) => (
              <div
                key={item.en}
                className={`flex-1 py-2.5 text-center ${
                  i < 2 ? "border-r border-[rgba(255,255,255,0.07)]" : ""
                }`}
              >
                <b className="block text-[15px] font-semibold leading-tight">{item.cn}</b>
                <span className="mt-0.5 block text-[8px] font-semibold uppercase tracking-[0.14em] text-[var(--lb-ink-3)]">
                  {item.en}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* ---- 表单 ---- */}
        <form onSubmit={submit} className="mt-auto pb-7 pt-8">
          <div className="flex items-baseline justify-between text-[9px] font-semibold uppercase tracking-[0.2em]">
            <span className={err ? "text-[var(--lb-danger)]" : "text-[var(--lb-ink-3)]"}>
              Access Code
            </span>
            <span className={err ? "text-[var(--lb-danger)]" : "text-[var(--lb-accent)]"}>
              {err ? "ERR" : "●"}
            </span>
          </div>

          <div
            key={attempt}
            className={`mt-2 rounded-[11px] border p-3 ${
              attempt > 0 && err ? "lb-shake" : ""
            }`}
            style={{
              borderColor: err ? "rgba(255,107,107,.42)" : "rgba(255,255,255,.14)",
              background: err ? "rgba(255,80,80,.07)" : "rgba(255,255,255,.055)",
              boxShadow: "inset 0 1px 0 rgba(255,255,255,.12)",
            }}
          >
            <div className={`lb-field ${err ? "is-error" : ""}`}>
              <input
                ref={inputRef}
                type={visible ? "text" : "password"}
                autoComplete="current-password"
                placeholder="输入访问口令"
                value={pass}
                onChange={(event) => {
                  setPass(event.target.value);
                  if (err) {
                    setErr("");
                  }
                }}
                aria-label="访问口令"
              />
              <button
                type="button"
                aria-label={visible ? "隐藏口令" : "显示口令"}
                onClick={() => setVisible((v) => !v)}
                className="grid shrink-0 place-items-center p-0.5 text-[var(--lb-ink-3)]"
              >
                {visible ? <EyeOff /> : <Eye />}
              </button>
            </div>

            <button
              type="submit"
              disabled={busy}
              className="mt-2 flex w-full items-center justify-center gap-2 rounded-[7px] py-3 text-[14px] font-bold text-[#0f0d16] transition-opacity duration-state disabled:opacity-60"
              style={{
                background: err ? "var(--lb-danger)" : "var(--lb-accent)",
                color: err ? "#1a0d0d" : "#0f0d16",
              }}
            >
              {busy ? "验证中…" : err ? "重试" : "进入训练场"}
              {busy ? <Spinner /> : <Arrow />}
            </button>
          </div>

          {err && (
            <p className="mt-2 text-[10px] leading-relaxed text-[rgba(255,160,160,.75)]">{err}</p>
          )}

          <p className="mt-3.5 text-center text-[10.5px] font-medium text-[var(--lb-ink-2)]">
            {MOTTO}
          </p>
          <p className="mt-1 text-center text-[9.5px] leading-relaxed text-[var(--lb-ink-3)]">
            训练记录、体重、伤痛只存这台服务器，不经过任何第三方
          </p>
        </form>
      </div>
    </div>
  );
}

/* ---------------- 图标 ---------------- */

function Eye() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOff() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden>
      <path d="M3 3l18 18" />
      <path d="M10.6 6.2A9.6 9.6 0 0 1 12 6c6 0 9.5 6 9.5 6a15.4 15.4 0 0 1-3.3 3.9" />
      <path d="M6.4 8A15.2 15.2 0 0 0 2.5 12S6 18 12 18a9.6 9.6 0 0 0 3.9-.8" />
    </svg>
  );
}

function Arrow() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M4 12h15M13 6l6 6-6 6" />
    </svg>
  );
}

function Spinner() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden className="animate-spin">
      <path d="M12 3a9 9 0 1 0 9 9" />
    </svg>
  );
}
