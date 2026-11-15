import { useNavigate } from "react-router-dom";
import type { CardBlock } from "../types";

type Props = {
  card: CardBlock;
};

export function ExerciseRefCards({ card }: Props) {
  const navigate = useNavigate();
  const items = card.items || [];
  if (!items.length) return null;

  return (
    <div className="mt-2.5 space-y-2">
      <p className="px-0.5 text-[11px] font-bold text-muted">相关动作</p>
      {items.map((item) => {
        const exerciseId = String(item.meta?.exercise_id || "").trim();
        const thumb = (item.meta?.thumb_url as string | null | undefined) || null;
        return (
          <button
            key={item.id}
            type="button"
            disabled={!exerciseId}
            onClick={() => {
              if (!exerciseId) return;
              navigate(`/exercises/${encodeURIComponent(exerciseId)}`, {
                state: { from: "coach" },
              });
            }}
            className="pressable flex w-full items-center gap-3 rounded-xl border border-line bg-elevated px-3 py-2.5 text-left disabled:opacity-50"
          >
            <div className="h-14 w-14 shrink-0 overflow-hidden rounded-lg border border-line bg-bg">
              {thumb ? (
                <img src={thumb} alt="" className="h-full w-full object-contain" />
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
      })}
    </div>
  );
}
