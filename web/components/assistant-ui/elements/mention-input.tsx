"use client";

import { useRef, useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { unstable_useComposerInput } from "@assistant-ui/react";
import { useMentionStore, type MentionItem } from "@/lib/mention-store";
import { mentionChipClass } from "@/lib/mention-colors";
import { encodeMentionsSuffix } from "@/lib/mention-encode";

const INPUT_SELECTOR = '[data-active="true"] div[data-role="mention-input"]';
const CHIP_BASE =
  "inline-block align-middle rounded px-1 py-0.5 mr-1 cursor-default whitespace-nowrap select-none";

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

let savedRange: Range | null = null;

export function saveMentionRange() {
  const el = document.querySelector<HTMLDivElement>(INPUT_SELECTOR);
  if (!el) return;
  const sel = window.getSelection();
  if (sel && sel.rangeCount) {
    const r = sel.getRangeAt(0);
    if (el.contains(r.endContainer)) {
      savedRange = r.cloneRange();
    }
  }
}

function createChipElement(m: MentionItem): HTMLSpanElement {
  const span = document.createElement("span");
  span.contentEditable = "false";
  span.setAttribute("data-mention", m.label);
  span.setAttribute("data-mention-info", JSON.stringify(m));
  span.className = CHIP_BASE + " " + mentionChipClass(m.type, m.table);
  span.textContent = `@${m.label}`;
  return span;
}

function dispatchInput(el: HTMLElement) {
  el.dispatchEvent(new InputEvent("input", { bubbles: true }));
}

function syncStoreFromDom(el: HTMLElement) {
  const chips = el.querySelectorAll<HTMLElement>("[data-mention]");
  const items: MentionItem[] = [];
  chips.forEach((chip) => {
    const info = chip.getAttribute("data-mention-info");
    if (info) {
      try {
        items.push(JSON.parse(info));
      } catch {}
    }
  });
  useMentionStore.getState().setAll(items);
}

function moveCursorAfter(node: Node) {
  const sel = window.getSelection();
  if (!sel) return;
  const range = document.createRange();
  range.setStartAfter(node);
  range.collapse(true);
  sel.removeAllRanges();
  sel.addRange(range);
}

export function insertMentionChip(m: MentionItem) {
  const el = document.querySelector<HTMLDivElement>(INPUT_SELECTOR);
  if (!el) {
    useMentionStore.getState().add(m);
    return;
  }
  el.focus();
  const sel = window.getSelection();
  if (!sel) return;

  if (savedRange) {
    sel.removeAllRanges();
    sel.addRange(savedRange);
  }

  if (!sel.rangeCount) {
    const chip = createChipElement(m);
    el.appendChild(chip);
    const space = document.createTextNode(" ");
    el.appendChild(space);
    moveCursorAfter(space);
    dispatchInput(el);
    syncStoreFromDom(el);
    savedRange = null;
    return;
  }

  const range = sel.getRangeAt(0);
  const node = range.endContainer;
  const offset = range.endOffset;

  if (node.nodeType === Node.TEXT_NODE && offset > 0) {
    const text = node.textContent ?? "";
    const atIdx = text.lastIndexOf("@", offset);
    if (atIdx >= 0) {
      const seg = text.slice(atIdx + 1, offset);
      if (seg.length <= 30) {
        const delRange = document.createRange();
        delRange.setStart(node, atIdx);
        delRange.setEnd(node, offset);
        delRange.deleteContents();
        const chip = createChipElement(m);
        delRange.insertNode(chip);
        const space = document.createTextNode(" ");
        chip.after(space);
        moveCursorAfter(space);
        dispatchInput(el);
        syncStoreFromDom(el);
        savedRange = null;
        return;
      }
    }
  }

  range.deleteContents();
  const chip = createChipElement(m);
  range.insertNode(chip);
  const space = document.createTextNode(" ");
  chip.after(space);
  moveCursorAfter(space);
  dispatchInput(el);
  syncStoreFromDom(el);
  savedRange = null;
}

export function insertTextAtCursor(text: string) {
  const el = document.querySelector<HTMLDivElement>(INPUT_SELECTOR);
  if (!el) return;
  el.focus();
  const sel = window.getSelection();
  if (!sel) return;
  if (savedRange) {
    sel.removeAllRanges();
    sel.addRange(savedRange);
  }
  if (!sel.rangeCount) {
    el.appendChild(document.createTextNode(text));
    dispatchInput(el);
    savedRange = null;
    return;
  }
  const range = sel.getRangeAt(0);
  range.deleteContents();
  const textNode = document.createTextNode(text);
  range.insertNode(textNode);
  range.setStartAfter(textNode);
  range.collapse(true);
  sel.removeAllRanges();
  sel.addRange(range);
  dispatchInput(el);
  savedRange = null;
}

const preventBlur = (e: React.MouseEvent) => e.preventDefault();

export function MentionInput({ autoFocus, isActive = true }: { autoFocus: boolean; isActive?: boolean }) {
  const { value, setText, send, canSend, isDisabled } = unstable_useComposerInput();
  const ref = useRef<HTMLDivElement>(null);
  const cacheRef = useRef<Record<string, Detail>>({});
  const [loadingKey, setLoadingKey] = useState<string | null>(null);
  const [hoverChip, setHoverChip] = useState<{
    rect: DOMRect;
    inputRect: DOMRect | null;
    m: MentionItem;
    key: string;
  } | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cardHoveredRef = useRef(false);

  const extractText = useCallback(() => {
    const el = ref.current;
    if (!el) return "";
    let text = "";
    const items: MentionItem[] = [];
    el.childNodes.forEach((node) => {
      if (node.nodeType === Node.TEXT_NODE) {
        text += node.textContent ?? "";
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        const e = node as HTMLElement;
        const label = e.getAttribute("data-mention");
        if (label !== null) {
          text += `@${label}`;
          const info = e.getAttribute("data-mention-info");
          if (info) {
            try {
              items.push(JSON.parse(info));
            } catch {}
          }
        } else {
          text += e.textContent ?? "";
        }
      }
    });
    return encodeMentionsSuffix(text, items);
  }, []);

  const syncMentions = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const chips = el.querySelectorAll<HTMLElement>("[data-mention]");
    const items: MentionItem[] = [];
    chips.forEach((chip) => {
      const info = chip.getAttribute("data-mention-info");
      if (info) {
        try {
          items.push(JSON.parse(info));
        } catch {}
      }
    });
    useMentionStore.getState().setAll(items);
  }, []);

  useEffect(() => {
    if (isActive) syncMentions();
  }, [isActive, syncMentions]);

  const sync = useCallback(() => {
    setText(extractText());
    syncMentions();
  }, [extractText, setText, syncMentions]);

  const handleInput = useCallback(() => {
    sync();
  }, [sync]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (canSend) send();
        return;
      }
      if (e.key === "Backspace") {
        const sel = window.getSelection();
        if (!sel || !sel.isCollapsed || !sel.rangeCount) return;
        const range = sel.getRangeAt(0);
        const node = range.endContainer;
        const offset = range.endOffset;
        let prev: Node | null = null;
        if (offset === 0 && node !== ref.current) {
          prev = node.previousSibling;
        } else if (node === ref.current && offset > 0) {
          prev = ref.current.childNodes[offset - 1] ?? null;
        }
        if (prev && prev.nodeType === Node.ELEMENT_NODE) {
          const chipEl = prev as HTMLElement;
          if (chipEl.hasAttribute("data-mention")) {
            e.preventDefault();
            chipEl.remove();
            sync();
          }
        }
      }
    },
    [canSend, send, sync],
  );

  const fetchDetail = useCallback(async (m: MentionItem, key: string) => {
    if (cacheRef.current[key]) return;
    setLoadingKey(key);
    try {
      const params = new URLSearchParams({ type: m.type, table: m.table });
      if (m.id !== undefined && m.id !== null) params.set("id", String(m.id));
      if (m.detail_table) params.set("detail_table", m.detail_table);
      if (m.datasource) params.set("datasource", m.datasource);
      const res = await fetch(`/api/forms/detail?${params.toString()}`);
      cacheRef.current[key] = (await res.json()) as Detail;
    } catch {
      cacheRef.current[key] = { error: "加载失败" };
    } finally {
      setLoadingKey(null);
      setHoverChip((prev) => (prev ? { ...prev } : null));
    }
  }, []);

  const cancelClose = useCallback(() => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }, []);

  const scheduleClose = useCallback(() => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => {
      if (cardHoveredRef.current) return;
      const card = document.querySelector(".aui-mention-card");
      if (card && card.contains(document.activeElement)) return;
      setHoverChip(null);
    }, 250);
  }, []);

  const openHover = useCallback(
    (chip: HTMLElement) => {
      cancelClose();
      const info = chip.getAttribute("data-mention-info");
      if (!info) return;
      try {
        const m = JSON.parse(info) as MentionItem;
        const key = keyOf(m);
        const inputRect = ref.current?.getBoundingClientRect() ?? null;
        setHoverChip({ rect: chip.getBoundingClientRect(), inputRect, m, key });
        fetchDetail(m, key);
      } catch {}
    },
    [fetchDetail, cancelClose],
  );

  const handleMouseOver = useCallback(
    (e: React.MouseEvent) => {
      const target = e.target as HTMLElement;
      const chip = target.closest("[data-mention]");
      if (chip) {
        openHover(chip as HTMLElement);
      } else {
        scheduleClose();
      }
    },
    [openHover, scheduleClose],
  );

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const adjust = () => {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 192) + "px";
    };
    const obs = new MutationObserver(adjust);
    obs.observe(el, { childList: true, characterData: true, subtree: true });
    adjust();
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const current = extractText();
    if (value !== current) {
      syncMentions();
      el.textContent = value;
      const sel = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(el);
      range.collapse(false);
      sel?.removeAllRanges();
      sel?.addRange(range);
    }
  }, [value, extractText, syncMentions]);

  const detail = hoverChip ? cacheRef.current[hoverChip.key] : undefined;
  const showCard = !!hoverChip;
  const cardWidth = hoverChip?.inputRect
    ? Math.max(hoverChip.inputRect.width, 560)
    : 560;
  const cardLeft = hoverChip?.inputRect
    ? Math.min(
        hoverChip.inputRect.left,
        (typeof window !== "undefined" ? window.innerWidth : 9999) - cardWidth - 8,
      )
    : hoverChip?.rect.left ?? 0;
  const showBelow = hoverChip ? hoverChip.rect.top < 320 : false;
  const cardTop = hoverChip
    ? showBelow
      ? hoverChip.rect.bottom - 2
      : hoverChip.rect.top + 2
    : 0;
  const cardTransform = showBelow ? "none" : "translateY(-100%)";

  return (
    <>
      <div
        ref={ref}
        data-role="mention-input"
        contentEditable={!isDisabled}
        suppressContentEditableWarning
        role="textbox"
        aria-label="Message input"
        aria-multiline="true"
        className="aui-composer-input max-h-48 min-h-10 w-full resize-none overflow-y-auto px-2.5 py-1 text-base leading-6 outline-none"
        onInput={handleInput}
        onKeyDown={handleKeyDown}
        onMouseOver={handleMouseOver}
        onMouseLeave={scheduleClose}
        onBlur={saveMentionRange}
      />
      {showCard
        ? createPortal(
            <div
              style={{
                position: "fixed",
                top: cardTop,
                left: cardLeft,
                width: cardWidth,
                transform: cardTransform,
                zIndex: 9999,
              }}
              onMouseEnter={() => {
                cardHoveredRef.current = true;
                cancelClose();
              }}
              onMouseLeave={() => {
                cardHoveredRef.current = false;
                scheduleClose();
              }}
            >
              <MentionCard
                loading={loadingKey === hoverChip!.key && !detail}
                detail={detail}
                mention={hoverChip!.m}
              />
            </div>,
            document.body,
          )
        : null}
    </>
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
                  onMouseDown={preventBlur}
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
          <div className="text-muted-foreground">
            {"明细表（点击引用）："}
          </div>
          <div className="mt-1 flex flex-wrap gap-1">
            {detail.detail_tables.map((d) => (
              <button
                key={d.detail_table}
                type="button"
                onMouseDown={preventBlur}
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
