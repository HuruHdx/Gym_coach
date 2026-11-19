import type { ReactNode } from "react";
import { Spinner } from "./Spinner";

type Kind = "loading" | "empty" | "error";

type Props = {
  kind: Kind;
  title?: string;
  desc?: ReactNode;
  action?: ReactNode;
  className?: string;
};

const DEFAULTS: Record<Kind, string> = {
  loading: "加载中…",
  empty: "暂无内容",
  error: "出了点问题",
};

/** 页面 / 列表区的加载、空态、错误占位 */
export function PageState({ kind, title, desc, action, className = "" }: Props) {
  return (
    <div
      className={`flex min-h-40 flex-col items-center justify-center gap-2 px-4 py-8 text-center text-muted ${className}`.trim()}
      role={kind === "error" ? "alert" : "status"}
    >
      {kind === "loading" ? <Spinner size={18} /> : null}
      <strong className={`text-sm font-semibold ${kind === "error" ? "text-danger" : "text-ink"}`}>
        {title || DEFAULTS[kind]}
      </strong>
      {desc ? <span className="max-w-[36em] text-meta leading-relaxed">{desc}</span> : null}
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}
