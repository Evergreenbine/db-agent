"use client";

import { useEffect, useRef, useState } from "react";
import type { UIMessage } from "ai";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { AssistantChatTransport, useChatRuntime } from "@assistant-ui/ai-sdk";
import { Thread } from "@/components/assistant-ui/thread.aui";
import { ConversationSidebar } from "@/components/conversation-sidebar";
import { UserMenu } from "@/components/user-menu";
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { useAuthStore } from "@/lib/auth-store";
import { useSessionStore } from "@/lib/session-store";
import { useMentionStore } from "@/lib/mention-store";
import { useComposerBridge } from "@/lib/composer-bridge";
import { useAui } from "@assistant-ui/react";
import { useAuiState } from "@assistant-ui/store";
import { Database, Brain } from "lucide-react";
import { ChangeFormCard } from "@/components/assistant-ui/change-form-card";
import { WriteConfirmCard } from "@/components/assistant-ui/write-confirm-card";

import KnowledgePage from "./knowledge/page";
import DatasourcesPage from "./datasources/page";

type HistoryMessage = {
  role: string;
  msg_type: string;
  content: string;
  raw_json?: string;
};

function historyText(content: string) {
  if (content.startsWith("【用户已 @ 引用的表单】")) {
    const parts = content.split("\n\n");
    return parts.at(-1) || content;
  }
  return content;
}

function safeJsonParse(s: string | undefined): Record<string, unknown> {
  if (!s) return {};
  try { return JSON.parse(s) as Record<string, unknown>; } catch { return {}; }
}

function toUiMessages(sessionId: string, messages: HistoryMessage[]): UIMessage[] {
  const result: UIMessage[] = [];
  let idx = 0;
  let pendingReasoning = "";
  const toolPartMap = new Map<string, Record<string, unknown>>();

  const newId = () => (idx === 0 ? sessionId : `${sessionId}-${idx}`);

  for (const msg of messages) {
    if (msg.msg_type === "message" && msg.role === "user") {
      result.push({
        id: newId(),
        role: "user",
        parts: [{ type: "text", text: historyText(msg.content) }],
      });
      idx++;
      pendingReasoning = "";
    } else if (msg.msg_type === "message" && msg.role === "assistant") {
      const parts: UIMessage["parts"] = [];
      if (pendingReasoning) {
        parts.push({ type: "reasoning", text: pendingReasoning });
        pendingReasoning = "";
      }
      parts.push({ type: "text", text: historyText(msg.content) });
      result.push({ id: newId(), role: "assistant", parts });
      idx++;
    } else if (msg.msg_type === "reasoning") {
      pendingReasoning += (pendingReasoning ? "\n" : "") + msg.content;
    } else if (msg.msg_type === "function_call") {
      const raw = safeJsonParse(msg.raw_json);
      const toolName = String(raw.name || "");
      const callId = String(raw.call_id || `call-${idx}`);
      let input: unknown = raw.arguments;
      if (typeof input === "string") {
        try { input = JSON.parse(input); } catch { /* keep string */ }
      }
      const toolPart: Record<string, unknown> = { type: `tool-${toolName}`, toolCallId: callId, state: "input-available", input };
      toolPartMap.set(callId, toolPart);
      const last = result[result.length - 1];
      if (last && last.role === "assistant") {
        (last.parts as unknown[]).push(toolPart);
      } else {
        const parts: UIMessage["parts"] = [];
        if (pendingReasoning) {
          parts.push({ type: "reasoning", text: pendingReasoning });
          pendingReasoning = "";
        }
        (parts as unknown[]).push(toolPart);
        result.push({ id: newId(), role: "assistant", parts });
        idx++;
      }
    } else if (msg.msg_type === "function_call_output") {
      const raw = safeJsonParse(msg.raw_json);
      const callId = String(raw.call_id || `call-${idx}`);
      let output: unknown = raw.output;
      if (typeof output === "string") {
        try { output = JSON.parse(output); } catch { /* keep string */ }
      }
      const toolPart2 = toolPartMap.get(callId);
      if (toolPart2) {
        toolPart2.state = "output-available";
        toolPart2.output = output;
      }
    }
  }

  return result;
}

export const Assistant = () => {
  const [activePanel, setActivePanel] = useState<"chat" | "knowledge" | "datasources">("chat");
  const [mountedChats, setMountedChats] = useState<Map<string, UIMessage[]>>(new Map());
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [historyVersion, setHistoryVersion] = useState(0);
  const [runningChats, setRunningChats] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (mountedChats.size === 0) {
      startNewConversation();
    }
  }, []);

  const handleRunningChange = (key: string, running: boolean) => {
    setRunningChats((prev) => {
      const next = new Set(prev);
      if (running) next.add(key);
      else next.delete(key);
      return next;
    });
  };

  const selectConversation = async (sessionId: string) => {
    if (mountedChats.has(sessionId)) {
      setActiveKey(sessionId);
      setActivePanel("chat");
      return;
    }
    const { token, user } = useAuthStore.getState();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    if (user?.employeeId) headers["X-Employee-Id"] = user.employeeId;
    const res = await fetch(
      `/api/history?session_id=${encodeURIComponent(sessionId)}`,
      { headers },
    );
    const data = await res.json();
    if (!res.ok) throw new Error(data?.detail || "历史对话加载失败");
    const messages = toUiMessages(sessionId, data.messages || []);
    setMountedChats((prev) => {
      const next = new Map(prev);
      if (next.size >= 5) {
        for (const key of next.keys()) {
          if (key !== activeKey) { next.delete(key); break; }
        }
      }
      next.set(sessionId, messages);
      return next;
    });
    setActiveKey(sessionId);
    setActivePanel("chat");
  };

  const startNewConversation = () => {
    const key = `new-${Date.now()}`;
    setMountedChats((prev) => {
      const next = new Map(prev);
      if (next.size >= 5) {
        for (const k of next.keys()) {
          if (k !== activeKey) { next.delete(k); break; }
        }
      }
      next.set(key, []);
      return next;
    });
    setActiveKey(key);
    setActivePanel("chat");
  };

  const refreshHistory = () => {
    window.setTimeout(() => setHistoryVersion((version) => version + 1), 1000);
  };

  return (
    <SidebarProvider defaultOpen={false}>
      <div className="flex h-dvh w-full pr-0.5">
        <ConversationSidebar
          activeSessionId={activeKey?.startsWith("new-") ? null : activeKey}
          refreshKey={historyVersion}
          onSelect={(sessionId) => void selectConversation(sessionId)}
          onNew={startNewConversation}
          runningChats={runningChats}
        />
        <SidebarInset className="relative">
          <header className="flex h-16 shrink-0 items-center gap-3 border-b pl-6 pr-4">
            <SidebarTrigger />
            <button
              onClick={() => setActivePanel(activePanel === "knowledge" ? "chat" : "knowledge")}
              className="ml-auto inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-lg px-3 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              title="记忆管理"
            >
              <Brain className="size-4" />
              <span className="hidden sm:inline">记忆</span>
            </button>
            <button
              onClick={() => setActivePanel(activePanel === "datasources" ? "chat" : "datasources")}
              className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-lg px-3 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
              title="数据源设置"
            >
              <Database className="size-4" />
              <span className="hidden sm:inline">数据源</span>
            </button>
            <UserMenu />
          </header>
          <div className="relative flex-1 overflow-hidden">
            {Array.from(mountedChats.entries()).map(([key, messages]) => (
              <div
                key={key}
                className="absolute inset-0"
                data-active={key === activeKey && activePanel === "chat" ? "true" : "false"}
                style={{ display: key === activeKey && activePanel === "chat" ? "block" : "none" }}
              >
                <AssistantChat
                  chatId={key}
                  initialMessages={messages}
                  isActive={key === activeKey && activePanel === "chat"}
                  onFinished={refreshHistory}
                  onRunningChange={(running) => handleRunningChange(key, running)}
                />
              </div>
            ))}
          </div>
          {activePanel === "knowledge" && (
            <div className="absolute inset-0 z-50 bg-background">
              <KnowledgePage onBack={() => setActivePanel("chat")} />
            </div>
          )}
          {activePanel === "datasources" && (
            <div className="absolute inset-0 z-50 bg-background">
              <DatasourcesPage onBack={() => setActivePanel("chat")} />
            </div>
          )}
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
};;


function ChatStateWatcher({ onRunningChange }: { onRunningChange: (running: boolean) => void }) {
  const isRunning = useAuiState((s) => s.thread.isRunning);
  const cbRef = useRef(onRunningChange);
  cbRef.current = onRunningChange;
  useEffect(() => {
    cbRef.current(isRunning);
  }, [isRunning]);
  return null;
}
function ComposerBridge({ isActive }: { isActive: boolean }) {
  const aui = useAui();
  useEffect(() => {
    if (!isActive) return;
    useComposerBridge.getState().setSendMessage((text: string) => {
      try {
        const c = aui.optional.composer;
        if (!c) { console.error("[ComposerBridge] composer not available"); return; }
        c.setText(text);
        setTimeout(() => { try { c.send(); } catch (e) { console.error("[ComposerBridge] send failed:", e); } }, 100);
      } catch (e) {
        console.error("[ComposerBridge] sendMessage failed:", e);
      }
    });
    return () => useComposerBridge.getState().setSendMessage(null);
  }, [aui, isActive]);
  return null;
}
function AssistantChat({
  chatId,
  initialMessages,
  onFinished,
  isActive,
  onRunningChange,
}: {
  chatId: string;
  initialMessages: UIMessage[];
  onFinished: () => void;
  isActive: boolean;
  onRunningChange: (running: boolean) => void;
}) {
    useEffect(() => {
    if (isActive) useSessionStore.getState().setSessionId(chatId);
  }, [chatId, isActive]);

const runtime = useChatRuntime({
    id: chatId,
    messages: initialMessages,
    transport: new AssistantChatTransport({
      api: "/api/chat",
      headers: () => {
        const { token, user } = useAuthStore.getState();
        const headers: Record<string, string> = {};
        if (token) headers.Authorization = `Bearer ${token}`;
        if (user?.employeeId) headers["X-Employee-Id"] = user.employeeId;
        const params = new URLSearchParams(window.location.search);
        const requestId = params.get("request_id");
        const sqr = params.get("sqr");
        if (requestId) headers["X-Request-Id"] = requestId;
        if (sqr) headers["X-SQR"] = sqr;
        const { mentions, clear } = useMentionStore.getState();
        if (mentions.length) {
          headers["X-Mentions"] = JSON.stringify(
            mentions.map(({ table, type, id, detail_table, datasource }) => ({
              table,
              type,
              id,
              detail_table,
              datasource,
            })),
          );
          clear();
        }
        return headers;
      },
    }),
    onFinish: onFinished,
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ChatStateWatcher onRunningChange={onRunningChange} />
      <ComposerBridge isActive={isActive} />
      <ChangeFormCard />
      <WriteConfirmCard />
      <Thread isActive={isActive} />
    </AssistantRuntimeProvider>
  );
}
