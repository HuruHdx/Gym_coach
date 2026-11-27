import { useNavigate } from "react-router-dom";
import { LoopClip } from "./LoopClip";
import type { CardBlock } from "../types";

type Props = {
  card: CardBlock;
};

function isVideoUrl(url: string | null | undefined): url is string {
  return Boolean(url && /\.(mp4|webm|mov)(\?|$)/i.test(url));
}

function RefCardItem({
  item,
  onOpen,
}: {
  item: CardBlock["items"][number];
  onOpen: (exerciseId: string) => void;
}) {
  const exerciseId = String(item.meta?.exercise_id || "").trim();
  const hasVideo = Boolean(item.meta?.has_video);
  const demoUrl = (item.meta?.demo_url as string | null | undefined) || null;
  const highlightUrl = (item.meta?.highlight_url as string | null | undefined) || null;
  // 教练卡：带声教学优先；无教学再降级静音示范
  const preferHighlight = hasVideo && isVideoUrl(highlightUrl);
  const preferDemo = !preferHighlight && hasVideo && isVideoUrl(demoUrl);
  const coverUrl =
    (item.meta?.cover_url as string | null | undefined) ||
    (item.meta?.thumb_url as string | null | undefined) ||
    null;
  const staticThumb = isVideoUrl(coverUrl) ? null : coverUrl;

  if (preferHighlight) {
    return (
      <div className="overflow-hidden rounded-xl border border-line bg-elevated">
        <div
          className="relative h-[150px] bg-bg"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        >
          <video
            src={highlightUrl}
            poster={staticThumb || undefined}
            className="h-full w-full object-contain"
            controls
            playsInline
            preload="metadata"
          />
          <span className="pointer-events-none absolute bottom-2.5 left-2.5 rounded-md bg-ink/55 px-1.5 py-0.5 text-[9px] font-bold text-white">
            教学视频 · 有声
          </span>
        </div>
        <button
          type="button"
          disabled={!exerciseId}
          onClick={() => {
            if (!exerciseId) return;
            onOpen(exerciseId);
          }}
          className="pressable flex w-full items-center gap-3 px-3.5 py-3 text-left disabled:opacity-50"
        >
          <div className="min-w-0 flex-1">
            <p className="truncate font-display text-sm font-bold text-ink">{item.title}</p>
            <p className="mt-0.5 text-[11px] text-muted">
              {item.subtitle || "查看示范与要领"}
            </p>
          </div>
          <span className="shrink-0 text-[11px] font-extrabold text-accent-text">详情</span>
        </button>
      </div>
    );
  }

  if (preferDemo) {
    return (
      <div className="overflow-hidden rounded-xl border border-line bg-elevated">
        <div
          className="relative h-[150px] bg-bg"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        >
          <LoopClip
            src={demoUrl}
            poster={staticThumb || undefined}
            lazy
            className="h-full w-full object-contain"
          />
          <span className="pointer-events-none absolute bottom-2.5 left-2.5 rounded-md bg-ink/55 px-1.5 py-0.5 text-[9px] font-bold text-white">
            静音示范
          </span>
        </div>
        <button
          type="button"
          disabled={!exerciseId}
          onClick={() => {
            if (!exerciseId) return;
            onOpen(exerciseId);
          }}
          className="pressable flex w-full items-center gap-3 px-3.5 py-3 text-left disabled:opacity-50"
        >
          <div className="min-w-0 flex-1">
            <p className="truncate font-display text-sm font-bold text-ink">{item.title}</p>
            <p className="mt-0.5 text-[11px] text-muted">
              {item.subtitle || "查看示范与要领"}
            </p>
          </div>
          <span className="shrink-0 text-[11px] font-extrabold text-accent-text">详情</span>
        </button>
      </div>
    );
  }

  return (
    <button
      type="button"
      disabled={!exerciseId}
      onClick={() => {
        if (!exerciseId) return;
        onOpen(exerciseId);
      }}
      className="pressable flex w-full items-center gap-3 rounded-xl border border-line bg-elevated px-3 py-2.5 text-left disabled:opacity-50"
    >
      <div className="h-14 w-14 shrink-0 overflow-hidden rounded-lg border border-line bg-bg">
        {staticThumb ? (
          <img src={staticThumb} alt="" className="h-full w-full object-contain" />
        ) : (
          <div className="grid h-full place-items-center text-[10px] font-bold text-muted">
            无图
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-display text-sm font-bold text-ink">{item.title}</p>
        <p className="mt-0.5 text-[11px] text-muted">
          {item.subtitle || "查看示范与要领"}
        </p>
      </div>
      <span className="shrink-0 text-[11px] font-extrabold text-accent-text">详情</span>
    </button>
  );
}

export function ExerciseRefCards({ card }: Props) {
  const navigate = useNavigate();
  const items = card.items || [];
  if (!items.length) return null;

  return (
    <div className="mt-2.5 space-y-2">
      <p className="px-0.5 text-[11px] font-bold text-muted">相关动作</p>
      {items.map((item) => (
        <RefCardItem
          key={item.id}
          item={item}
          onOpen={(exerciseId) => {
            navigate(`/exercises/${encodeURIComponent(exerciseId)}`, {
              state: { from: "coach" },
            });
          }}
        />
      ))}
    </div>
  );
}
