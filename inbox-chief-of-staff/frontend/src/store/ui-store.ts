import { create } from "zustand";
import type { Priority } from "@/types";

interface UIState {
  selectedMessageId: string | null;
  activeInboxFilter: Priority | "all";
  isBriefPanelOpen: boolean;
  setSelectedMessage: (id: string | null) => void;
  setInboxFilter: (filter: Priority | "all") => void;
  setBriefPanelOpen: (open: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  selectedMessageId: null,
  activeInboxFilter: "all",
  isBriefPanelOpen: false,
  setSelectedMessage: (id) => set({ selectedMessageId: id }),
  setInboxFilter: (filter) => set({ activeInboxFilter: filter }),
  setBriefPanelOpen: (open) => set({ isBriefPanelOpen: open }),
}));
