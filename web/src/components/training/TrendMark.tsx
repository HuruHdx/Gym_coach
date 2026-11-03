import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import type { Trend } from "./sessionStats";

const LABEL: Record<Trend, string> = {
  up: "进步",
  down: "退步",
  flat: "持平",
  new: "首次",
};

export function TrendMark({ trend }: { trend: Trend }) {
  const tone =
    trend === "up" ? "text-ok" : trend === "down" ? "text-danger" : trend === "new" ? "text-ink" : "text-muted";
  const Icon = trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : trend === "flat" ? Minus : null;
  return (
    <span className={`inline-flex items-center gap-0.5 text-[10px] font-extrabold ${tone}`}>
      {Icon && <Icon size={12} strokeWidth={2.25} />}
      {LABEL[trend]}
    </span>
  );
}
