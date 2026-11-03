import { create } from "zustand";
import { persist } from "zustand/middleware";

/** 对齐 gym-ui/tokens.css 的 data-theme */
export type Skin = "lavender" | "mint" | "dark";

const LEGACY: Record<string, Skin> = {
  court: "lavender",
  cobalt: "mint",
  ember: "lavender",
};

type SkinState = {
  skin: Skin;
  setSkin: (s: Skin) => void;
};

function normalize(raw: unknown): Skin {
  if (raw === "lavender" || raw === "mint" || raw === "dark") return raw;
  if (typeof raw === "string" && raw in LEGACY) return LEGACY[raw];
  return "lavender";
}

export const useSkinStore = create<SkinState>()(
  persist(
    (set) => ({
      skin: "lavender",
      setSkin: (skin) => set({ skin: normalize(skin) }),
    }),
    {
      name: "gym-skin",
      merge: (persisted, current) => {
        const p = (persisted || {}) as Partial<SkinState>;
        return { ...current, ...p, skin: normalize(p.skin ?? current.skin) };
      },
    },
  ),
);
