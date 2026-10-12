import { useState, type FormEvent } from "react";
import { api, markAuthed, setToken } from "../lib/api";

type Props = { onDone: () => void };

export function LoginPage({ onDone }: Props) {
  const [pass, setPass] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    const token = pass.trim();
    if (!token) {
      setErr("请输入访问口令");
      return;
    }
    setBusy(true);
    setErr("");
    try {
      setToken(token);
      await api("/api/auth/verify");
      markAuthed();
      onDone();
    } catch {
      setErr("口令不对，或后端没开。本地默认是 dev-token");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="noise mx-auto flex h-dvh max-w-md flex-col bg-bg px-5 pb-8 pt-12">
      <div className="relative z-10 flex flex-1 flex-col">
        <div
          className="pointer-events-none absolute -right-10 top-0 h-48 w-48 rounded-full border-[18px] border-accent/25"
          aria-hidden
        />
        <p className="font-display text-xs font-extrabold uppercase tracking-[0.14em] text-muted">
          Gym Coach
        </p>
        <h1 className="font-display mt-4 text-[42px] font-extrabold leading-[0.95] tracking-tight">
          先登录
          <br />
          再开练<span className="text-accent">.</span>
        </h1>
        <p className="mt-3 max-w-[24ch] text-sm leading-relaxed text-muted">
          个人部署用访问口令解锁。登录后可以建画像，也可以先跳过。
        </p>

        <form onSubmit={submit} className="mt-10 space-y-3 rise-in rise-in-delay-1">
          <label className="block">
            <span className="text-[11px] font-bold uppercase tracking-widest text-muted">
              访问口令
            </span>
            <input
              type="password"
              autoComplete="current-password"
              className="mt-2 w-full rounded-md border border-line bg-elevated px-4 py-3 font-display text-lg font-bold outline-none focus:border-ink"
              placeholder="例如 dev-token"
              value={pass}
              onChange={(e) => setPass(e.target.value)}
            />
          </label>
          {err && <p className="text-sm font-semibold text-danger">{err}</p>}
          <button
            type="submit"
            disabled={busy}
            className="pressable w-full rounded-md bg-accent py-3.5 font-display text-base font-extrabold text-accent-ink disabled:opacity-60"
          >
            {busy ? "验证中…" : "进入"}
          </button>
        </form>

        <button
          type="button"
          className="mt-3 text-left text-xs font-semibold text-muted underline"
          onClick={() => {
            setPass("dev-token");
          }}
        >
          填入本地默认口令
        </button>

        <p className="mt-auto pt-8 text-xs leading-relaxed text-muted">
          口令对应服务器上的 <code className="text-ink">APP_TOKEN</code>
          。以后多人再用账号体系也不影响这套入口。
        </p>
      </div>
    </div>
  );
}
