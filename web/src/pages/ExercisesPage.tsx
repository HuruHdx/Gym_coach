import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useInfiniteQuery } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";
import { api } from "../lib/api";
import { MUSCLE_OPTIONS } from "../types";

type CatalogItem = {
  id: string;
  name_zh: string;
  name_en: string | null;
  muscle: string | null;
  sub_region: string | null;
  gear: string | null;
  coach_core: boolean;
  thumb_url: string | null;
};

type CatalogPage = {
  total: number;
  page: number;
  page_size: number;
  items: CatalogItem[];
};

const PAGE_SIZE = 24;

export function ExercisesPage() {
  const navigate = useNavigate();
  const [draftQ, setDraftQ] = useState("");
  const [q, setQ] = useState("");
  const [muscle, setMuscle] = useState("全部");

  useEffect(() => {
    const timer = window.setTimeout(() => setQ(draftQ.trim()), 280);
    return () => window.clearTimeout(timer);
  }, [draftQ]);

  const query = useInfiniteQuery({
    queryKey: ["catalog-exercises", q, muscle],
    initialPageParam: 1,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams();
      params.set("page", String(pageParam));
      params.set("page_size", String(PAGE_SIZE));
      if (q) params.set("q", q);
      if (muscle !== "全部") params.set("muscle", muscle);
      return api<CatalogPage>(`/api/exercises?${params}`);
    },
    getNextPageParam: (last) => {
      const loaded = last.page * last.page_size;
      return loaded < last.total ? last.page + 1 : undefined;
    },
  });

  const items = useMemo(
    () => query.data?.pages.flatMap((page) => page.items) ?? [],
    [query.data],
  );
  const total = query.data?.pages[0]?.total ?? 0;

  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3 rise-in">
      <button
        type="button"
        onClick={() => navigate("/training")}
        className="pressable -ml-1 mb-2 inline-flex w-fit items-center gap-0.5 text-[12px] font-bold text-muted"
      >
        <ChevronLeft size={16} />
        训练
      </button>
      <h1 className="font-display text-[26px] font-bold tracking-tight">动作库</h1>
      <p className="mt-1 text-[12px] text-muted">
        {query.isLoading ? "加载中…" : `${total} 个动作`}
      </p>

      <input
        value={draftQ}
        onChange={(e) => setDraftQ(e.target.value)}
        placeholder="搜中文名 / 英文 / 别名 / ID"
        className="mt-3 w-full rounded-xl border border-line bg-elevated px-3.5 py-2.5 text-base outline-none placeholder:text-muted focus:border-ink"
      />

      <div className="no-scrollbar mt-3 flex gap-1.5 overflow-x-auto pb-1">
        {["全部", ...MUSCLE_OPTIONS].map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setMuscle(item)}
            className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-bold ${
              muscle === item ? "bg-accent text-accent-ink" : "border border-line bg-elevated text-muted"
            }`}
          >
            {item}
          </button>
        ))}
      </div>

      {query.isError && (
        <p className="mt-4 text-sm text-danger">加载失败，请稍后重试。</p>
      )}
      {!query.isLoading && items.length === 0 && (
        <p className="mt-4 text-sm text-muted">没有匹配的动作。</p>
      )}

      <div className="mt-3 grid grid-cols-2 gap-2.5">
        {items.map((item) => (
          <Link
            key={item.id}
            to={`/exercises/${encodeURIComponent(item.id)}`}
            className="pressable overflow-hidden rounded-2xl border border-line bg-elevated"
          >
            <div className="relative aspect-square bg-bg">
              {item.thumb_url ? (
                <img
                  src={item.thumb_url}
                  alt=""
                  className="h-full w-full object-contain"
                  loading="lazy"
                />
              ) : (
                <div className="grid h-full place-items-center text-[11px] font-bold text-muted">
                  暂无图
                </div>
              )}
              {item.coach_core ? (
                <span className="absolute left-1.5 top-1.5 rounded bg-ink/85 px-1.5 py-0.5 text-[9px] font-extrabold text-accent">
                  主力
                </span>
              ) : null}
            </div>
            <div className="px-2.5 py-2">
              <p className="truncate text-[13px] font-bold leading-tight">{item.name_zh}</p>
              <p className="mt-0.5 truncate text-[11px] text-muted">
                {[item.muscle, item.sub_region, item.gear].filter(Boolean).join(" · ") || "—"}
              </p>
            </div>
          </Link>
        ))}
      </div>

      {query.hasNextPage ? (
        <button
          type="button"
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
          className="pressable mt-4 rounded-xl border border-line bg-elevated py-2.5 text-sm font-bold text-muted"
        >
          {query.isFetchingNextPage ? "加载中…" : "加载更多"}
        </button>
      ) : null}
    </div>
  );
}
