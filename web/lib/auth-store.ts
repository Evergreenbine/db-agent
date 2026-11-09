import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface AuthUser {
  employeeId: string;
  name: string;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  login: (user: AuthUser, token: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      login: (user, token) => set({ user, token }),
      logout: () => set({ token: null, user: null }),
    }),
    { name: "oa-agent-auth" },
  ),
);
