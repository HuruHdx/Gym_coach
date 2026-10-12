import { create } from "zustand";
import { persist } from "zustand/middleware";

export type Skin = "court" | "cobalt" | "ember";

type SkinState = {
  skin: Skin;
  setSkin: (s: Skin) => void;
};

export const useSkinStore = create<SkinState>()(
  persist(
    (set) => ({
      skin: "court",
      setSkin: (skin) => set({ skin }),
    }),
    { name: "gym-skin" },
  ),
);
