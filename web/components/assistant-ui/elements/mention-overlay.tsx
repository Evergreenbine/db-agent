"use client";

import { useEffect, useRef, useState, useCallback, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useMentionStore, type MentionItem } from "@/lib/mention-store";
import { mentionChipClass } from "@/lib/mention-colors";

const INPUT_SELECTOR = 'textarea[aria-label="Message input"]';
const TEXT_CLASS = "whitespace-pre-wrap break-words px-2.5 py-1 text-base leading-6";

// Chip: light blue bg + dark blue text + blue border, WITH padding.
// Drift compensation in the render loop keeps the caret aligned despite padding.
const CHIP_BASE =
  "pointer-events-auto inline-block align-middle leading-5 rounded px-1 py-0.5 mr-0.5";
const CHIP_FALLBACK =
  CHIP_BASE + " bg-blue-50 text-blue-700 [outline:1px_solid_var(--color-blue-300)]";

// Extra width each chip adds beyond its text: px-1 (0.5rem) + mr-0.5 (0.125rem).
const CHIP_EXTRA_REM = 0.625;

function escapeRegex(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

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
  field_count?: number;
};

const TYPE_LABEL: Record<MentionItem["type"], string> = {
  workflow: "流程表单",
  modeled: "建模表单",
  builtin: "系统内置表",
  datasource: "数据源表",
};

const keyOf = (m: MentionItem) =>
  `${m.table}|${m.id ?? ""}|${m.detail_table ?? ""}`;

/** Insert a mention chip token (@label) at the textarea cursor and register it. */
export function insertMentionToken(m: MentionItem) {
  const ta = document.querySelector<HTMLTextAreaElement>(INPUT_SELECTOR);
  const token = `@${m.label}`;
  if (!ta) {
    useMentionStore.getState().add(m);
    return;
  }
  ta.focus();
  const start = ta.selectionStart ?? ta.value.length;
  const end = ta.selectionEnd ?? ta.value.length;
  ta.setRangeText(token, start, end, "end");
  ta.dispatchEvent(new InputEvent("input", { bubbles: true }));
  useMentionStore.getState().add(m);
}

/** Insert plain text at cursor (field name click). */
function insertTextAtCursor(text: string) {
  const ta = document.querySelector<HTMLTextAreaElement>(INPUT_SELECTOR);
  if (!ta) return;
  ta.focus();
  const s = ta.selectionStart ?? ta.value.length;
  const e = ta.selectionEnd ?? ta.value.length;
  ta.setRangeText(text, s, e, "end");
  ta.dispatchEvent(new InputEvent("input", { bubbles: true }));
}

function tokenize(value: string, labels: string[]) {
  if (!labels.length || !value)
    return [{ text: value, chip: false, label: "" }];
  const sorted = [...new Set(labels)].sort((a, b) => b.length - a.length);
  const re = new RegExp("@(?:" + sorted.map(escapeRegex).join("|") + ")", "g");
  const parts: { text: string; chip: boolean; label: string }[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(value)) !== null) {
    if (m.index > last)
      parts.push({ text: value.slice(last, m.index), chip: false, label: "" });
    parts.push({ text: m[0], chip: true, label: m[0].slice(1) });
    last = m.index + m[0].length;
    if (re.lastIndex === m.index) re.lastIndex++;
  }
  if (last < value.length)
    parts.push({ text: value.slice(last), chip: false, label: "" });
  return parts;
}

export function MentionOverlay() {
  const mentions = useMentionStore((s) => s.mentions);
  const [value, setValue] = useState("");
  const [scrollTop, setScrollTop] = useState(0);
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const [taRect, setTaRect] = useState<{ left: number; width: number } | null>(null);
  const cacheRef = useRef<Record<string, Detail>>({});
  const [loadingKey, setLoadingKey] = useState<string | null>(null);

  const labels = mentions.map((m) => m.label);

  const fetchDetail = useCallback(async (m: MentionItem) => {
    const key = keyOf(m);
    if (cacheRef.current[key]) return;
    setLoadingKey(key);
    try {
      const params = new URLSearchParams({ type: m.type, table: m.table });
      if (m.id !== undefined && m.id !== null) params.set("id", String(m.id));
      if (m.detail_table) params.set("detail_table", m.detail_table);
      const res = await fetch(`/api/forms/detail?${params.toString()}`);
      cacheRef.current[key] = (await res.json()) as Detail;
    } catch {
      cacheRef.current[key] = { error: "加载失败" };
    } finally {
      setLoadingKey(null);
    }
  }, []);

  useEffect(() => {
    let ta: HTMLTextAreaElement | null = null;
    let attached = false;
    const sync = () => {
      if (!ta) return;
      setValue(ta.value);
      setScrollTop(ta.scrollTop);
      const r = ta.getBoundingClientRect();
      setTaRect({ left: r.left, width: r.width });
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Backspace" || !ta) return;
      const pos = ta.selectionStart;
      if (pos === null || pos !== ta.selectionEnd) return;
      const before = ta.value.slice(0, pos);
      const ms = useMentionStore.getState().mentions;
      const sorted = [...ms.map((m) => m.label)].sort(
        (a, b) => b.length - a.length,
      );
      for (const lbl of sorted) {
        const tok = `@${lbl}`;
        if (before.endsWith(tok)) {
          e.preventDefault();
          const start = pos - tok.length;
          ta.setRangeText("", start, pos, "end");
          ta.dispatchEvent(new InputEvent("input", { bubbles: true }));
          useMentionStore.getState().removeByLabel(lbl);
          return;
        }
      }
    };
    const attach = (n: number) => {
      ta = document.querySelector<HTMLTextAreaElement>(INPUT_SELECTOR);
      if (!ta) {
        if (n < 25) setTimeout(() => attach(n + 1), 100);
        return;
      }
      ta.addEventListener("input", sync);
      ta.addEventListener("click", sync);
      ta.addEventListener("keyup", sync);
      ta.addEventListener("scroll", sync);
      ta.addEventListener("keydown", onKey);
      attached = true;
      sync();
    };
    attach(0);
    return () => {
      if (ta && attached) {
        ta.removeEventListener("input", sync);
        ta.removeEventListener("click", sync);
        ta.removeEventListener("keyup", sync);
        ta.removeEventListener("scroll", sync);
        ta.removeEventListener("keydown", onKey);
      }
    };
  }, []);

  const parts = tokenize(value, labels);

  // Drift compensation: chips carry padding the transparent textarea
  // doesn't see. Pull each following element left by the accumulated
  // chip-extra width so the overlay caret stays aligned with the real one.
  const rendered: ReactNode[] = [];
  let drift = 0;
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i];
    if (p.chip) {
      const ml = drift;
      drift += CHIP_EXTRA_REM;
      rendered.push(
        <InlineChip
          key={`chip-${i}-${p.label}`}
          label={p.label}
          mention={mentions.find((m) => m.label === p.label)}
          hoverKey={hoverKey}
          setHoverKey={setHoverKey}
          loadingKey={loadingKey}
          cache={cacheRef.current}
          fetchDetail={fetchDetail}
          taRect={taRect}
          marginLeftRem={ml}
        />,
      );
    } else if (p.text === "") {
      continue;
    } else {
      const ml = drift;
      drift = 0;
      rendered.push(
        <span key={`txt-${i}`} style={{ marginLeft: `-${ml}rem` }}>
          {p.text}
        </span>,
      );
    }
  }

  return (
    <div
      aria-hidden="true"
      className="aui-mention-overlay pointer-events-none absolute inset-0 z-10 overflow-hidden"
    >
      <div
        className={TEXT_CLASS}
        style={{ transform: `translateY(-${scrollTop}px)` }}
      >
        {rendered.length === 0 ? <span>&#8203;</span> : null}
        {rendered}
      </div>
    </div>
  );
}

function InlineChip({
  label,
  mention,
  hoverKey,
  setHoverKey,
  loadingKey,
  cache,
  fetchDetail,
  taRect,
  marginLeftRem,
}: {
  label: string;
  mention?: MentionItem;
  hoverKey: string | null;
  setHoverKey: (k: string | null) => void;
  loadingKey: string | null;
  cache: Record<string, Detail>;
  fetchDetail: (m: MentionItem) => void;
  taRect: { left: number; width: number } | null;
  marginLeftRem: number;
}) {
  const chipRef = useRef<HTMLSpanElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const key = mention ? keyOf(mention) : label;
  const detail = mention ? cache[key] : undefined;

  const open = () => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    setHoverKey(key);
    if (chipRef.current)
      setRect(chipRef.current.getBoundingClientRect());
    if (mention) fetchDetail(mention);
  };
  const close = () => {
    closeTimer.current = setTimeout(() => setHoverKey(null), 150);
  };

  if (!mention) {
    return (
      <span
        className={CHIP_FALLBACK}
        style={{ marginLeft: `-${marginLeftRem}rem` }}
      >{`@${label}`}</span>
    );
  }

  const showCard = hoverKey === key && rect;
  const cardWidth = Math.max(taRect?.width ?? 400, 560);
  const cardLeft = Math.min(
    taRect?.left ?? rect!.left,
    (typeof window !== "undefined" ? window.innerWidth : 9999) - cardWidth - 8,
  );
  return (
    <span
      className="relative inline-block align-middle leading-5"
      style={{ marginLeft: `-${marginLeftRem}rem` }}
    >
      <span
        ref={chipRef}
        className={CHIP_BASE + " " + mentionChipClass(mention.type, mention.table)}
        onMouseEnter={open}
        onMouseLeave={close}
      >
        {`@${label}`}
      </span>
      {showCard
        ? createPortal(
            <div
              style={{
                position: "fixed",
                top: rect!.top,
                left: cardLeft,
                width: cardWidth,
                transform: "translateY(-100%)",
                zIndex: 9999,
              }}
              onMouseEnter={open}
              onMouseLeave={close}
            >
              <MentionCard
                loading={loadingKey === key && !detail}
                detail={detail}
                mention={mention}
              />
            </div>,
            document.body,
          )
        : null}
    </span>
  );
}

function MentionCard({
  loading,
  detail,
  mention,
}: {
  loading: boolean;
  detail?: Detail;
  mention: MentionItem;
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
        (r) =>
          r.col.toLowerCase().includes(ql) ||
          r.cn.toLowerCase().includes(ql),
      )
    : fieldRows;
  return (
    <div className="aui-mention-card w-full rounded-lg border bg-popover p-4 text-xs shadow-xl">
      <div className="text-sm font-medium text-foreground">{mention.label}</div>
      <div className="mt-0.5 text-muted-foreground">
        物理表{" "}
        <span className="font-mono text-foreground">
          {detail?.table ?? mention.table}
        </span>
        <span className="ml-2">[{TYPE_LABEL[mention.type]}]</span>
      </div>
      {detail?.module ? (
        <div className="text-muted-foreground">模块：{detail.module}</div>
      ) : null}
      {loading ? (
        <div className="mt-2 text-muted-foreground">加载字段中...</div>
      ) : detail?.error ? (
        <div className="mt-2 text-destructive">{detail.error}</div>
      ) : fieldRows.length > 0 ? (
        <div className="mt-2">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜索字段..."
            className="mb-1.5 w-full rounded border bg-background px-2 py-1 text-xs outline-none focus:border-primary"
          />
          <div>
            <div className="mb-1 text-muted-foreground">
              字段（{filtered.length}/{fieldRows.length}，点击插入）：
            </div>
            <div className="space-y-0.5">
              {filtered.map((r, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => insertTextAtCursor(r.col + " ")}
                  className="flex w-full gap-2 rounded px-1.5 py-1 text-left hover:bg-accent"
                  title={`插入 ${r.col}`}
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
                  无匹配字段
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
      {detail?.detail_tables && detail.detail_tables.length > 0 ? (
        <div className="mt-2 border-t pt-2">
          <div className="text-muted-foreground">明细表（点击引用）：</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {detail.detail_tables.map((d) => (
              <button
                key={d.detail_table}
                type="button"
                onClick={() =>
                  insertMentionToken({
                    table: d.detail_table,
                    type: mention.type,
                    id: mention.id,
                    label: d.detail_table,
                    detail_table: d.detail_table,
                  })
                }
                className="rounded bg-accent px-1.5 py-0.5 font-mono text-[10px] text-foreground transition-colors hover:bg-primary hover:text-primary-foreground"
                title={`${d.detail_table}（${d.field_count}字段）`}
              >
                {d.detail_table}
                <span className="ml-1 text-muted-foreground/70">
                  {d.field_count}
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
