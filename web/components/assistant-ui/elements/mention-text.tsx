"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { TextMessagePartComponent } from "@assistant-ui/react";
import { decodeMentionsSuffix, type EncodedMention } from "@/lib/mention-encode";
import { ExecResultMessage, isExecMessage } from "./exec-result-message";
import { mentionBadgeClass } from "@/lib/mention-colors";
import {
  insertTextAtCursor,
  insertMentionChip,
} from "@/components/assistant-ui/elements/mention-input";

type DetailField = {
  field?: string;
  name?: string;
  label?: string | null;
  chinese_name?: string | null;
  db_type?: string | null;
  data_type?: string | null;
};
type Detail = {
  table?: string;
  chinese_name?: string;
  label?: string;
  module?: string;
  pk?: string;
  main_fields?: DetailField[];
  fields?: DetailField[];
  detail_tables?: { detail_table: string; field_count: number }[];
  error?: string;
};

const TYPE_LABEL: Record<EncodedMention["type"], string> = {
  workflow: "流程表单",
  modeled: "建模表单",
  builtin: "系统内置表",
  datasource: "数据源表",
};

const CARD_WIDTH = 288; // w-72
const GAP = 8;

type Segment =
  | { kind: "text"; value: string }
  | { kind: "mention"; m: EncodedMention };

function splitByMentions(text: string, mentions: EncodedMention[]): Segment[] {
  const segs: Segment[] = [];
  let remaining = text;
  const consumed = new Set<number>();
  while (remaining) {
  let best: { idx: number; end: number; mIdx: number } | null = null;
  for (let i = 0; i < mentions.length; i++) {
    const m = mentions[i];
    if (consumed.has(i)) continue;
      const token = "@" + m.label;
      const idx = remaining.indexOf(token);
      if (idx >= 0 && (best === null || idx < best.idx)) {
        best = { idx, end: idx + token.length, mIdx: i };
      }
  }
    if (!best) {
      segs.push({ kind: "text", value: remaining });
      break;
    }
    if (best.idx > 0) segs.push({ kind: "text", value: remaining.slice(0, best.idx) });
    segs.push({ kind: "mention", m: mentions[best.mIdx] });
    consumed.add(best.mIdx);
    remaining = remaining.slice(best.end);
  }
  return segs;
}

function MentionCardContent({
  loading,
  detail,
  mention,
}: {
  loading: boolean;
  detail: Detail | null;
  mention: EncodedMention;
}) {
  const [q, setQ] = useState("");
  const fields = detail?.main_fields ?? detail?.fields ?? [];
  const fieldRows = fields.map((f) => ({
    col: f.field ?? f.name ?? "",
    cn: f.label ?? f.chinese_name ?? "",
    type: f.db_type ?? f.data_type ?? "",
  }));
  const ql = q.trim().toLowerCase();
  const filtered = ql
    ? fieldRows.filter(
        (r) => r.col.toLowerCase().includes(ql) || r.cn.toLowerCase().includes(ql),
      )
    : fieldRows;
  return (
    <div className="aui-mention-card w-full rounded-lg border bg-popover p-4 text-xs shadow-xl">
      <div className="text-sm font-medium text-foreground">{mention.label}</div>
      <div className="mt-0.5 text-muted-foreground">
        {"物理表"}{" "}
        <span className="font-mono text-foreground">
          {detail?.table ?? mention.table}
        </span>
        <span className="ml-2">[{mention.type === "datasource" ? (mention.datasource ?? "数据源") : TYPE_LABEL[mention.type]}]</span>
      </div>
      {detail?.module ? (
        <div className="text-muted-foreground">{"模块："}{detail.module}</div>
      ) : null}
      {loading ? (
        <div className="mt-2 text-muted-foreground">{"加载字段中"}...</div>
      ) : detail?.error ? (
        <div className="mt-2 text-destructive">{detail.error}</div>
      ) : fieldRows.length > 0 ? (
        <div className="mt-2">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={"搜索字段..."}
            className="mb-1.5 w-full rounded border bg-background px-2 py-1 text-xs outline-none focus:border-primary"
          />
          <div className="max-h-60 overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            <div className="mb-1 text-muted-foreground">
              {"字段（"}{filtered.length}/{fieldRows.length}{"，点击插入）："}
            </div>
            <div className="space-y-0.5">
              {filtered.map((r, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => insertTextAtCursor(r.col + " ")}
                  className="flex w-full gap-2 rounded px-1.5 py-1 text-left hover:bg-accent"
                  title={"插入 " + r.col}
                >
                  <span className="shrink-0 font-mono text-foreground">{r.col}</span>
                  <span className="text-muted-foreground">{r.cn}</span>
                  {r.type ? (
                    <span className="ml-auto shrink-0 text-muted-foreground/70">
                      {r.type}
                    </span>
                  ) : null}
                </button>
              ))}
              {filtered.length === 0 ? (
                <div className="py-2 text-center text-muted-foreground">
                  {"无匹配字段"}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
      {detail?.detail_tables && detail.detail_tables.length > 0 ? (
        <div className="mt-2 border-t pt-2">
          <div className="text-muted-foreground">{"明细表（点击引用）："}</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {detail.detail_tables.map((d) => (
              <button
                key={d.detail_table}
                type="button"
                onClick={() =>
                  insertMentionChip({
                    table: d.detail_table,
                    type: mention.type,
                    id: mention.id,
                    label: d.detail_table,
                    detail_table: d.detail_table,
                  })
                }
                className="rounded bg-accent px-1.5 py-0.5 font-mono text-[10px] text-foreground transition-colors hover:bg-primary hover:text-primary-foreground"
                title={d.detail_table + " (" + d.field_count + ")"}
              >
                {d.detail_table}
                <span className="ml-1 text-muted-foreground/70">{d.field_count}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function MentionTag({ m }: { m: EncodedMention }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<Detail | null>(null);
  const cacheRef = useRef<Detail | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const anchorRef = useRef<HTMLSpanElement | null>(null);
  const cardRef = useRef<HTMLDivElement | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  const fetchDetail = useCallback(async () => {
    if (cacheRef.current) {
      setDetail(cacheRef.current);
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({ type: m.type, table: m.table });
      if (m.id != null) params.set("id", String(m.id));
      if (m.detail_table) params.set("detail_table", m.detail_table);
      if (m.datasource) params.set("datasource", m.datasource);
      const res = await fetch("/api/forms/detail?" + params.toString());
      cacheRef.current = (await res.json()) as Detail;
      setDetail(cacheRef.current);
    } catch {
      cacheRef.current = { error: "加载失败" };
      setDetail(cacheRef.current);
    } finally {
      setLoading(false);
    }
  }, [m]);

  const cancelClose = useCallback(() => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }, []);

  const computePos = useCallback(() => {
    const anchor = anchorRef.current;
    if (!anchor) return;
    const r = anchor.getBoundingClientRect();
    const cardH = cardRef.current?.offsetHeight ?? 320;
    let top = r.top - cardH - GAP;
    if (top < 8) top = r.bottom + GAP; // 上方放不下则向下
    let left = r.left;
    if (left + CARD_WIDTH > (typeof window !== "undefined" ? window.innerWidth : 9999) - 8)
      left = (typeof window !== "undefined" ? window.innerWidth : 9999) - CARD_WIDTH - 8;
    if (left < 8) left = 8;
    setPos({ top, left });
  }, []);

  const onEnter = useCallback(() => {
    cancelClose();
    setOpen(true);
    fetchDetail();
  }, [cancelClose, fetchDetail]);

  const onLeave = useCallback(() => {
    closeTimer.current = setTimeout(() => setOpen(false), 120);
  }, []);

  // 卡片高度变化（详情加载完）时重算位置
  useLayoutEffect(() => {
    if (open) computePos();
  }, [open, detail, loading, computePos]);

  useEffect(() => {
    if (!open) return;
    const onScroll = () => computePos();
    window.addEventListener("scroll", onScroll, true);
    return () => window.removeEventListener("scroll", onScroll, true);
  }, [open, computePos]);

  return (
    <span
      ref={anchorRef}
      className="relative inline-flex"
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
    >
      <span
        className={"inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium cursor-default " + mentionBadgeClass(m.type, m.table)}
      >
        <span className="max-w-[12rem] truncate">{"@" + m.label}</span>
      </span>
      {open && pos && typeof document !== "undefined"
        ? createPortal(
            <div
              ref={cardRef}
              style={{ position: "fixed", top: pos.top, left: pos.left, zIndex: 50 }}
              className="w-72"
              onMouseEnter={cancelClose}
              onMouseLeave={onLeave}
            >
              <MentionCardContent loading={loading} detail={detail} mention={m} />
            </div>,
            document.body,
          )
        : null}
    </span>
  );
}

export const UserMessageText: TextMessagePartComponent = (part) => {
  const raw = (part as { text?: string }).text ?? "";
  if (isExecMessage(raw)) {
    return <ExecResultMessage text={raw} />;
  }
  const { text, mentions } = decodeMentionsSuffix(raw);
  if (mentions.length === 0) {
    return <>{text}</>;
  }
  const segs = splitByMentions(text, mentions);
  return (
    <>
      {segs.map((s, i) =>
        s.kind === "text" ? (
          <span key={i}>{s.value}</span>
        ) : (
          <MentionTag key={i} m={s.m} />
        ),
      )}
    </>
  );
};
