"use client";

import * as React from "react";
import { useCallback, useEffect, useState } from "react";
import { MessagesSquare, PlusIcon, Trash2Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarRail,
} from "@/components/ui/sidebar";
import { useAuthStore } from "@/lib/auth-store";

type Conversation = {
  session_id: string;
  title: string;
  msg_count: number;
  updated_at: string;
};

function cleanTitle(title: string | undefined) {
  const text = title || "";
  if (text.startsWith("【用户已 @ 引用的表单】")) {
    const parts = text.split("\n\n");
    return parts.at(-1)?.trim() || "未命名对话";
  }
  return text || "未命名对话";
}

function formatTime(value: string) {
  const date = new Date(value.replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return value;
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  if (isToday) {
    return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
}

function groupByDate(items: Conversation[]) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const groups: { label: string; items: Conversation[] }[] = [
    { label: "今天", items: [] },
    { label: "昨天", items: [] },
    { label: "更早", items: [] },
  ];
  for (const c of items) {
    const d = new Date((c.updated_at || "").replace(" ", "T"));
    if (isNaN(d.getTime())) {
      groups[2].items.push(c);
    } else if (d >= today) {
      groups[0].items.push(c);
    } else if (d >= yesterday) {
      groups[1].items.push(c);
    } else {
      groups[2].items.push(c);
    }
  }
  return groups.filter((g) => g.items.length > 0);
}

export function ConversationSidebar({
  activeSessionId,
  refreshKey,
  onSelect,
  onNew,
}: {
  activeSessionId: string | null;
  refreshKey: number;
  onSelect: (sessionId: string) => void;
  onNew: () => void;
}) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const { token, user } = useAuthStore.getState();
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;
      if (user?.employeeId) headers["X-Employee-Id"] = user.employeeId;
      const query = user?.employeeId
        ? `?user_id=${encodeURIComponent(user.employeeId)}`
        : "";
      const res = await fetch(`/api/history${query}`, { headers });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || data?.error || "历史加载失败");
      setConversations(data.conversations || []);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const remove = async (sessionId: string) => {
    const { token, user } = useAuthStore.getState();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    if (user?.employeeId) headers["X-Employee-Id"] = user.employeeId;
    await fetch(`/api/history?session_id=${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
      headers,
    });
    if (activeSessionId === sessionId) onNew();
    void load();
  };

  const groups = groupByDate(conversations);

  return (
    <Sidebar style={{ "--sidebar-width": "17.5rem" } as React.CSSProperties}>
      <SidebarHeader className="px-3 pb-3 pt-3.5">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
            <MessagesSquare className="size-4" />
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-[15px] font-semibold">小e</span>
            <span className="text-[11px] text-muted-foreground">
              数据库执行智能体
            </span>
          </div>
        </div>
      </SidebarHeader>
      <SidebarContent className="scrollbar-hide px-3">
        <Button
          variant="default"
          size="sm"
          className="mb-3 w-full justify-center gap-2 rounded-lg py-2.5 text-sm font-medium shadow-sm"
          onClick={onNew}
        >
          <PlusIcon className="size-4" />
          新对话
        </Button>
        {loading ? (
          <div className="flex flex-col gap-1.5 px-1 py-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-14 animate-pulse rounded-lg bg-muted/50" />
            ))}
          </div>
        ) : error ? (
          <div className="mx-1 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
            {error}
          </div>
        ) : conversations.length === 0 ? (
          <div className="px-3 py-8 text-center text-sm text-muted-foreground">
            暂无历史对话
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {groups.map((group) => (
              <div key={group.label} className="flex flex-col gap-0.5">
                <div className="px-2.5 pb-1 pt-1.5 text-[11px] font-medium tracking-wide text-muted-foreground/50">
                  {group.label}
                </div>
                {group.items.map((c) => {
                  const active = c.session_id === activeSessionId;
                  return (
                    <div
                      key={c.session_id}
                      className={`flex items-stretch rounded-lg transition-colors ${
                        active ? "bg-accent" : "hover:bg-accent/40"
                      }`}
                    >
                      <button
                        type="button"
                        className="flex min-w-0 flex-1 flex-col gap-1 py-2.5 pl-2.5 pr-2 text-left"
                        onClick={() => onSelect(c.session_id)}
                        title={cleanTitle(c.title)}
                      >
                        <span
                          className={`line-clamp-2 text-[13px] leading-snug ${
                            active ? "font-medium text-foreground" : "text-foreground/80"
                          }`}
                        >
                          {cleanTitle(c.title)}
                        </span>
                        <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                          <span className="tabular-nums">{c.msg_count} 条</span>
                          <span className="text-muted-foreground/30">·</span>
                          <span className="tabular-nums">{formatTime(c.updated_at)}</span>
                        </span>
                      </button>
                      <button
                        type="button"
                        className="flex w-7 shrink-0 items-center justify-center rounded-r-lg opacity-0 transition-opacity hover:opacity-100 hover:text-destructive"
                        onClick={() => void remove(c.session_id)}
                        title="删除对话"
                      >
                        <Trash2Icon className="size-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        )}
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  );
}
