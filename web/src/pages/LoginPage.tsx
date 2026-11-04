import { useEffect, useRef, useState, type FormEvent } from "react";
import { markAuthed, setToken } from "../lib/api";
import { MOTTO } from "../lib/brand";

type Props = { onDone: () => void };
type Mode = "login" | "register";

/**
 * 登录页（品牌页）。
 *
 * 深色 + 荧光黄绿只在 .login-brand 作用域内。
 * 认证：手机号 + 密码；POST /api/auth/login 或 /register。
 */
export function LoginPage({ onDone }: Props) {
  const [mode, setMode] = useState<Mode>("login");
  const [phone, setPhone] = useState("");
  const [pass, setPass] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [hint, setHint] = useState("");
  /** 每次失败递增，用来重放抖动动画。 */
  const [attempt, setAttempt] = useState(0);
  const phoneRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (err) phoneRef.current?.focus();
  }, [err]);

  async function postAuth(path: "/api/auth/login" | "/api/auth/register") {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone: phone.trim(), password: pass }),
    });
    const text = await res.text();
    let detail = "";
    try {
      const body = JSON.parse(text) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* ignore */
    }
    if (!res.ok) {
      throw new Error(detail || `${res.status}: ${text}`);
    }
    if (!text) return {};
    return JSON.parse(text) as Record<string, unknown>;
  }

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    if (busy) return;
    const p = phone.trim();
    if (!/^1[3-9]\d{9}$/.test(p)) {
      setErr("请输入 11 位手机号");
      setHint("");
      setAttempt((n) => n + 1);
      return;
    }
    if (pass.length < 6) {
      setErr("密码至少 6 位");
      setHint("");
      setAttempt((n) => n + 1);
      return;
    }
    setBusy(true);
    setErr("");
    setHint("");
    try {
      if (mode === "register") {
        await postAuth("/api/auth/register");
        // 注册成功不自动进 App：切回登录，让用户主动登一次
        setMode("login");
        setPass("");
        setHint("注册成功，请用手机号登录");
        return;
      }
      const data = await postAuth("/api/auth/login");
      const token = data.access_token;
      if (typeof token !== "string" || !token) {
        throw new Error("登录失败");
      }
      setToken(token);
      markAuthed();
      onDone();
    } catch (error) {
      setErr(error instanceof Error ? error.message : mode === "login" ? "登录失败" : "注册失败");
      setAttempt((n) => n + 1);
    } finally {
      setBusy(false);
    }
  }

  function switchMode(next: Mode) {
    setMode(next);
    setErr("");
    setHint("");
  }

  return (
    <div className="login-brand mx-auto flex h-dvh max-w-md flex-col">
      <div className="lb-sky" aria-hidden />
      <div className="lb-plate" aria-hidden />

      <div className="lb-wrap flex-1">
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

        <div className="mt-11">
          <p
            className={`text-[9.5px] font-semibold uppercase tracking-[0.26em] ${
              err ? "text-[var(--lb-danger)]" : "text-[var(--lb-accent)]"
            }`}
          >
            {err ? "Access Denied" : "Personal Training Log"}
          </p>
          <h1 className="mt-3 font-display text-[46px] font-bold italic leading-[0.96] tracking-[-0.045em]">
            {mode === "login" ? (
              <>
                先登录
                <br />
                再开练
                <span className="not-italic">.</span>
              </>
            ) : (
              <>
                注册账号
                <br />
                开练
                <span className="not-italic">.</span>
              </>
            )}
          </h1>
          <p className="mt-4 font-display text-[17px] font-medium tracking-[-0.01em] text-[var(--lb-ink-2)]">
            赶紧训练吧彦祖
          </p>

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

        <form onSubmit={submit} className="mt-auto pb-7 pt-8">
          <div className="mb-3 flex gap-4 text-[9px] font-semibold uppercase tracking-[0.2em]">
            <button
              type="button"
              onClick={() => switchMode("login")}
              className={
                mode === "login" ? "text-[var(--lb-accent)]" : "text-[var(--lb-ink-3)]"
              }
            >
              登录
            </button>
            <button
              type="button"
              onClick={() => switchMode("register")}
              className={
                mode === "register" ? "text-[var(--lb-accent)]" : "text-[var(--lb-ink-3)]"
              }
            >
              注册
            </button>
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
                ref={phoneRef}
                type="tel"
                inputMode="numeric"
                autoComplete="tel"
                placeholder="手机号"
                value={phone}
                maxLength={11}
                onChange={(event) => {
                  setPhone(event.target.value.replace(/\D/g, "").slice(0, 11));
                  if (err) setErr("");
                }}
                aria-label="手机号"
              />
            </div>

            <div className={`lb-field mt-2 ${err ? "is-error" : ""}`}>
              <input
                type={visible ? "text" : "password"}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
                placeholder={mode === "register" ? "密码（至少 6 位）" : "密码"}
                value={pass}
                onChange={(event) => {
                  setPass(event.target.value);
                  if (err) setErr("");
                }}
                aria-label="密码"
              />
              <button
                type="button"
                aria-label={visible ? "隐藏密码" : "显示密码"}
                onClick={() => setVisible((v) => !v)}
                className="grid shrink-0 place-items-center p-0.5 text-[var(--lb-ink-3)]"
              >
                {visible ? <EyeOff /> : <Eye />}
              </button>
            </div>

            <button
              type="submit"
              disabled={busy}
              className="mt-2 flex w-full items-center justify-center gap-2 rounded-[7px] py-3 text-[14px] font-bold transition-opacity duration-state disabled:opacity-60"
              style={{
                background: err ? "var(--lb-danger)" : "var(--lb-accent)",
                color: err ? "#1a0d0d" : "#0f0d16",
              }}
            >
              {busy
                ? "请稍候…"
                : err
                  ? "重试"
                  : mode === "login"
                    ? "进入训练场"
                    : "注册"}
              {busy ? <Spinner /> : <Arrow />}
            </button>
          </div>

          {err && (
            <p className="mt-2 text-[10px] leading-relaxed text-[rgba(255,160,160,.75)]">{err}</p>
          )}
          {!err && hint && (
            <p className="mt-2 text-center text-[10px] leading-relaxed text-[var(--lb-accent)]">
              {hint}
            </p>
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
