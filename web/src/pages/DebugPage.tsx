import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";

type Trace = {
  id: number;
  created_at: string;
  user_text: string;
  payload: Record<string, unknown>;
};

export function DebugPage() {
  const { data, refetch, isFetching } = useQuery({
    queryKey: ["traces"],
    queryFn: () => api<Trace[]>("/api/debug/traces?limit=10"),
  });

  return (
    <div className="flex-1 px-4 pb-4 pt-3">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Debug</h1>
        <Link to="/me" className="text-sm text-muted">
          返回
        </Link>
      </div>
      <p className="mt-1 text-xs text-muted">意图 → 记忆包 → 模型 → 块。点刷新拉取最新。</p>
      <button
        type="button"
        onClick={() => refetch()}
        className="mt-3 rounded-md border border-line px-3 py-1.5 text-xs font-bold"
      >
        {isFetching ? "刷新中…" : "刷新"}
      </button>
      <div className="mt-4 space-y-3">
        {(data || []).map((t) => (
          <details key={t.id} className="rounded-md border border-line bg-elevated p-3">
            <summary className="cursor-pointer font-display text-sm font-bold">
              #{t.id} · {t.user_text}
            </summary>
            <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-[11px] text-muted">
              {JSON.stringify(t.payload, null, 2)}
            </pre>
          </details>
        ))}
        {!data?.length && <p className="text-sm text-muted">还没有轨迹。去今日说一句试试。</p>}
      </div>
    </div>
  );
}
