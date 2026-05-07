import { create } from "zustand";
import type { Priority } from "@/types";

interface UIState {
  selectedMessageId: string | null;
  activeInboxFilter: Priority | "all";
  correctionModalMessageId: string | null;
  setSelectedMessage: (id: string | null) => void;
  setInboxFilter: (filter: Priority | "all") => void;
  openCorrectionModal: (id: string) => void;
  closeCorrectionModal: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  selectedMessageId: null,
  activeInboxFilter: "urgent",
  correctionModalMessageId: null,
  setSelectedMessage: (id) => set({ selectedMessageId: id }),
  setInboxFilter: (filter) => set({ activeInboxFilter: filter }),
  openCorrectionModal: (id) => set({ correctionModalMessageId: id }),
  closeCorrectionModal: () => set({ correctionModalMessageId: null }),
}));
