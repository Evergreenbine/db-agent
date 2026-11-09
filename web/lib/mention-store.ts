import { create } from "zustand";

export interface MentionItem {
  table: string;
  type: "workflow" | "modeled" | "builtin" | "datasource";
  id?: number;
  label: string;
  detail_table?: string;
  datasource?: string;
}

interface MentionState {
  mentions: MentionItem[];
  add: (m: MentionItem) => void;
  remove: (index: number) => void;
  removeByLabel: (label: string) => void;
  setAll: (items: MentionItem[]) => void;
  clear: () => void;
}

export const useMentionStore = create<MentionState>((set) => ({
  mentions: [],
  add: (m) => set((s) => ({ mentions: [...s.mentions, m] })),
  remove: (index) =>
    set((s) => ({ mentions: s.mentions.filter((_, i) => i !== index) })),
  removeByLabel: (label) =>
    set((s) => {
      const idx = s.mentions.map((m) => m.label).lastIndexOf(label);
      if (idx < 0) return s;
      return { mentions: s.mentions.filter((_, i) => i !== idx) };
    }),
  setAll: (items) => set({ mentions: items }),
  clear: () => set({ mentions: [] }),
}));
