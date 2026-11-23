import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useInfiniteQuery } from "@tanstack/react-query";
import { ChevronLeft, Search, X } from "lucide-react";
import { api } from "../lib/api";
import { MUSCLE_OPTIONS } from "../types";

type CatalogItem = {
  id: string;
  name_zh: string;
  name_en: string | null;
  muscle: string | null;
  sub_region: string | null;
  gear: string | null;
  modality: string | null;
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
const GEAR_OPTIONS = ["自由重量", "器械", "绳索", "自重"] as const;
const MODALITY_OPTIONS = ["抗阻", "有氧", "HIIT", "灵活性"] as const;

export function ExercisesPage() {
  const navigate = useNavigate();
  const [draftQ, setDraftQ] = useState("");
  const [q, setQ] = useState("");
  const [muscle, setMuscle] = useState("全部");
  const [gear, setGear] = useState<string | null>(null);
  const [modality, setModality] = useState<string | null>(null);
  const [coreOnly, setCoreOnly] = useState(false);
  const [gearOpen, setGearOpen] = useState(false);
  const [modalityOpen, setModalityOpen] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setQ(draftQ.trim()), 280);
    return () => window.clearTimeout(timer);
  }, [draftQ]);

  const query = useInfiniteQuery({
    queryKey: ["catalog-exercises", q, muscle, gear, modality, coreOnly],
    initialPageParam: 1,
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams();
      params.set("page", String(pageParam));
      params.set("page_size", String(PAGE_SIZE));
      if (q) params.set("q", q);
      if (muscle !== "全部") params.set("muscle", muscle);
      if (gear) params.set("gear", gear);
      if (modality) params.set("modality", modality);
      if (coreOnly) params.set("coach_core", "true");
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
  const activeTags = [
    gear ? { key: "gear", label: gear } : null,
    modality ? { key: "modality", label: modality } : null,
    coreOnly ? { key: "core", label: "只看主力" } : null,
  ].filter(Boolean) as { key: string; label: string }[];

  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3 rise-in">
      <button
        type="button"
        onClick={() => navigate("/training")}
        className="pressable -ml-1 mb-1 inline-flex w-fit items-center gap-0.5 text-[12px] font-bold text-muted"
      >
        <ChevronLeft size={16} />
        训练
      </button>
      <h1 className="font-display text-[26px] font-extrabold tracking-tight">动作库</h1>
      <p className="mt-1 text-[12px] text-muted">{query.isLoading ? "加载中…" : `${total} 个动作`}</p>

      <label className="mt-3 flex items-center gap-2 rounded-xl border border-line bg-elevated px-3.5 py-2.5">
        <Search size={16} className="text-muted" />
        <input
          value={draftQ}
          onChange={(e) => setDraftQ(e.target.value)}
          placeholder="搜中文名 / 英文 / 别名"
          className="w-full bg-transparent text-sm outline-none placeholder:text-muted"
        />
      </label>

      <div className="no-scrollbar mt-3 flex gap-1.5 overflow-x-auto pb-1">
        {["全部", ...MUSCLE_OPTIONS.filter((m) => m !== "全身")].map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setMuscle(item)}
            className={`shrink-0 rounded-lg px-3 py-1.5 text-[11.5px] font-bold ${
              muscle === item
                ? "bg-ink text-[color:var(--accent-ink,#fff)]"
                : "border border-line bg-elevated text-muted"
            }`}
          >
            {item}
          </button>
        ))}
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        <FilterPill
          label={gear ? `器械 · ${gear}` : "器械"}
          active={Boolean(gear)}
          onClick={() => {
            setGearOpen((v) => !v);
            setModalityOpen(false);
          }}
        />
        <FilterPill
          label={modality ? `课型 · ${modality}` : "课型"}
          active={Boolean(modality)}
          onClick={() => {
            setModalityOpen((v) => !v);
            setGearOpen(false);
          }}
        />
        <FilterPill
          label="只看主力"
          active={coreOnly}
          solid
          onClick={() => setCoreOnly((v) => !v)}
        />
      </div>

      {gearOpen && (
        <div className="no-scrollbar mt-2 flex gap-1.5 overflow-x-auto pb-1">
          {GEAR_OPTIONS.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => {
                setGear(gear === item ? null : item);
                setGearOpen(false);
              }}
              className={`shrink-0 rounded-lg px-3 py-1.5 text-[11px] font-bold ${
                gear === item ? "bg-tint text-accent-text" : "border border-line bg-elevated text-muted"
              }`}
            >
              {item}
            </button>
          ))}
        </div>
      )}
      {modalityOpen && (
        <div className="no-scrollbar mt-2 flex gap-1.5 overflow-x-auto pb-1">
          {MODALITY_OPTIONS.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => {
                setModality(modality === item ? null : item);
                setModalityOpen(false);
              }}
              className={`shrink-0 rounded-lg px-3 py-1.5 text-[11px] font-bold ${
                modality === item
                  ? "bg-tint text-accent-text"
                  : "border border-line bg-elevated text-muted"
              }`}
            >
              {item}
            </button>
          ))}
        </div>
      )}

      {activeTags.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {activeTags.map((tag) => (
            <button
              key={tag.key}
              type="button"
              onClick={() => {
                if (tag.key === "gear") setGear(null);
                if (tag.key === "modality") setModality(null);
                if (tag.key === "core") setCoreOnly(false);
              }}
              className="pressable inline-flex items-center gap-1 rounded-md bg-tint px-2 py-1 text-[10.5px] font-bold text-accent-text"
            >
              {tag.label}
              <X size={12} />
            </button>
          ))}
          <button
            type="button"
            className="text-[11px] font-bold text-muted"
            onClick={() => {
              setGear(null);
              setModality(null);
              setCoreOnly(false);
            }}
          >
            清除全部
          </button>
        </div>
      )}

      {query.isError && <p className="mt-4 text-sm text-danger">加载失败，请稍后重试。</p>}
      {!query.isLoading && !query.isError && items.length === 0 && (
        <p className="mt-8 text-center text-sm text-muted">没有符合条件的动作</p>
      )}

      <div className="mt-4 grid grid-cols-2 gap-2.5">
        {items.map((item) => (
          <Link
            key={item.id}
            to={`/exercises/${encodeURIComponent(item.id)}`}
            state={{ fromCatalog: true }}
            className="pressable overflow-hidden rounded-2xl border border-line bg-elevated"
          >
            <div className="relative aspect-[4/3] bg-tint">
              {item.thumb_url ? (
                <img src={item.thumb_url} alt="" className="h-full w-full object-cover" loading="lazy" />
              ) : (
                <div className="grid h-full place-items-center text-muted">🏋️</div>
              )}
              {item.coach_core && (
                <span className="absolute left-2 top-2 rounded bg-ink/85 px-1.5 py-0.5 text-[9px] font-extrabold text-[color:var(--accent-ink,#ece7fb)]">
                  主力
                </span>
              )}
            </div>
            <div className="px-2.5 py-2">
              <p className="truncate text-[13px] font-bold">{item.name_zh}</p>
              <p className="mt-0.5 truncate text-[10.5px] text-muted">
                {[item.muscle, item.sub_region, item.gear].filter(Boolean).join(" · ") || "—"}
              </p>
            </div>
          </Link>
        ))}
      </div>

      {query.hasNextPage && (
        <button
          type="button"
          disabled={query.isFetchingNextPage}
          onClick={() => void query.fetchNextPage()}
          className="pressable mt-4 w-full rounded-xl border border-line py-2.5 text-sm font-bold disabled:opacity-60"
        >
          {query.isFetchingNextPage ? "加载中…" : "加载更多"}
        </button>
      )}
    </div>
  );
}

function FilterPill({
  label,
  active,
  onClick,
  solid,
}: {
  label: string;
  active?: boolean;
  onClick: () => void;
  solid?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`pressable rounded-[9px] px-2.5 py-1.5 text-[11.5px] font-bold ${
        active && solid
          ? "bg-accent text-accent-ink"
          : active
            ? "border border-[color-mix(in_srgb,var(--accent)_35%,transparent)] bg-tint text-accent-text"
            : "border border-line bg-elevated text-[color:var(--text-2,#54506b)]"
      }`}
    >
      {label}
    </button>
  );
}
