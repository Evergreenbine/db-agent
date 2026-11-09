import { create } from "zustand";

interface SessionState {
  sessionId: string;
  setSessionId: (id: string) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessionId: "",
  setSessionId: (id: string) => set({ sessionId: id }),
}));
