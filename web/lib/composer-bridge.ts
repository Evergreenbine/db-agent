"use client";

import { create } from "zustand";

type SendMessageFn = (text: string) => void;

interface ComposerBridgeState {
  sendMessage: SendMessageFn | null;
  setSendMessage: (fn: SendMessageFn | null) => void;
}

export const useComposerBridge = create<ComposerBridgeState>((set) => ({
  sendMessage: null,
  setSendMessage: (fn) => set({ sendMessage: fn }),
}));
