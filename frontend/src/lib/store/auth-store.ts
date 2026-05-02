"use client";
import { create } from "zustand";
import type { UserOut } from "@/types/api";

interface AuthState {
  user: UserOut | null;
  setUser: (user: UserOut | null) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  setUser: (user) => set({ user }),
  clear: () => set({ user: null }),
}));
