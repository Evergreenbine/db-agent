"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { mentionBadgeClass } from "@/lib/mention-colors";
import { insertMentionChip, saveMentionRange } from "@/components/assistant-ui/elements/mention-input";
import type { MentionType } from "@/lib/mention-colors";
import { pinyin } from "pinyin-pro";

type FormItem = {
  id?: number;
  table: string;
  chinese_name?: string;
  module?: string;
  datasource?: string;
  row_count?: number;
  ref_count?: number;
};
type DsGroup = {
  name: string;
  label: string;
  db_type: string;
  tables: FormItem[];
};
type FormsData = {
  builtin: FormItem[];
  workflow: FormItem[];
  modeled: FormItem[];
  datasources?: DsGroup[];
};

const CATEGORIES = [
  { id: "workflow", label: "流程表单" },
  { id: "modeled", label: "建模表单" },
  { id: "builtin", label: "系统内置表" },
] as const;
type OaCatId = (typeof CATEGORIES)[number]["id"];
type CatId = OaCatId | string; // OA 三类，或 "ds:<数据源名>"

const PAGE_SIZE = 30;
const INIT_VISIBLE = 30;
const INPUT_SELECTOR = '[data-active="true"] div[data-role="mention-input"]';

export function MentionPicker({ isActive = true }: { isActive?: boolean } = {}) {
  const [data, setData] = useState<FormsData | null>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cat, setCat] = useState<CatId>("workflow");
  const [activeIdx, setActiveIdx] = useState(0);
  const [visibleCount, setVisibleCount] = useState(INIT_VISIBLE);
  const listRef = useRef<HTMLDivElement | null>(null);
  const pinyinMap = useRef<Map<string, { full: string; abbr: string }>>(new Map());

  useEffect(() => {
    fetch("/api/forms")
      .then((r) => r.json())
      .then((raw: FormsData) => {
        const pm = new Map<string, { full: string; abbr: string }>();
        const compute = (items: FormItem[]) => {
          for (const it of items) {
            const name = it.chinese_name ?? "";
            if (name) {
              try {
                pm.set(it.table, {
                  full: (pinyin(name, { toneType: "none", type: "array" }) as string[]).join("").toLowerCase(),
                  abbr: (pinyin(name, { pattern: "first", toneType: "none", type: "array" }) as string[]).join("").toLowerCase(),
                });
              } catch { /* skip */ }
            }
          }
        };
        compute(raw.builtin ?? []);
        compute(raw.workflow ?? []);
        compute(raw.modeled ?? []);
        for (const ds of raw.datasources ?? []) compute(ds.tables);
        pinyinMap.current = pm;
        setData(raw);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!isActive) {
      setOpen(false);
      return;
    }
    const el = document.querySelector<HTMLDivElement>(INPUT_SELECTOR);
    if (!el) return;

    const handler = () => {
      const sel = window.getSelection();
      if (!sel || !sel.rangeCount || !sel.isCollapsed) {
        setOpen(false);
        return;
      }
      const range = sel.getRangeAt(0);
      if (!el.contains(range.endContainer)) {
        setOpen(false);
        return;
      }
      const node = range.endContainer;
      const offset = range.endOffset;
      if (node.nodeType !== Node.TEXT_NODE) {
        setOpen(false);
        return;
      }
      const text = node.textContent ?? "";
      const atIdx = text.lastIndexOf("@", offset - 1);
      if (atIdx === -1) {
        setOpen(false);
        return;
      }
      const seg = text.slice(atIdx + 1, offset);
      if (seg.length > 30) {
        setOpen(false);
        return;
      }
      saveMentionRange();
      setQuery(seg);
      setActiveIdx(0);
      setVisibleCount(INIT_VISIBLE);
      setOpen(true);
    };

    const keyHandler = (e: KeyboardEvent) => {
      if (!open) return;
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        setOpen(false);
        return;
      }
      const items = currentItems();
      if (e.key === "ArrowDown") {
        e.preventDefault();
        e.stopPropagation();
        setActiveIdx((i) => Math.min(i + 1, items.length - 1));
        scrollActive();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        e.stopPropagation();
        setActiveIdx((i) => Math.max(i - 1, 0));
        scrollActive();
      } else if (e.key === "Enter" && items[activeIdx]) {
        e.preventDefault();
        e.stopPropagation();
        insertItem(items[activeIdx]);
      }
    };

    el.addEventListener("input", handler);
    el.addEventListener("click", handler);
    el.addEventListener("keyup", handler);
    el.addEventListener("keydown", keyHandler);
    return () => {
      el.removeEventListener("input", handler);
      el.removeEventListener("click", handler);
      el.removeEventListener("keyup", handler);
      el.removeEventListener("keydown", keyHandler);
    };
  }, [open, activeIdx, cat, query, data, isActive]);

  const catList = (): FormItem[] => {
    if (!data) return [];
    if (cat.startsWith("ds:")) {
      const name = cat.slice(3);
      return data.datasources?.find((d) => d.name === name)?.tables ?? [];
    }
    return data[cat as OaCatId] ?? [];
  };

  const filteredItems = (): FormItem[] => {
    if (!data) return [];
    const q = query.toLowerCase().trim();
    const list = catList();
    if (!q) return list;
    return list.filter((it) => {
      if ((it.chinese_name ?? "").toLowerCase().includes(q)) return true;
      if ((it.table ?? "").toLowerCase().includes(q)) return true;
      const py = pinyinMap.current.get(it.table);
      if (py && (py.full.includes(q) || py.abbr.includes(q))) return true;
      return false;
    });
  };

  const currentItems = (): FormItem[] => filteredItems().slice(0, visibleCount);

  const currentMentionType = (): MentionType =>
    cat.startsWith("ds:") ? "datasource" : (cat as OaCatId);

  const scrollActive = () => {
    requestAnimationFrame(() => {
      const el = listRef.current?.querySelector<HTMLElement>(
        `[data-idx="${activeIdx}"]`,
      );
      el?.scrollIntoView({ block: "nearest" });
    });
  };

  const insertItem = (it: FormItem) => {
    const isDs = cat.startsWith("ds:");
    const text = it.chinese_name || it.table;
    insertMentionChip({
      table: it.table,
      type: currentMentionType(),
      id: isDs ? undefined : it.id,
      label: text,
      datasource: isDs ? cat.slice(3) : undefined,
    });
    if (it.table) {
      fetch("/api/forms/track?table=" + encodeURIComponent(it.table), { method: "POST" }).catch(() => {});
    }
    setOpen(false);
  };

  if (!open || !data) return null;
  const items = currentItems();
  const total = filteredItems().length;

  return (
    <div
      data-slot="mention-picker"
      className="aui-mention-picker absolute bottom-full left-0 z-50 mb-2 flex max-h-80 w-[560px] flex-col rounded-lg border bg-popover shadow-lg"
    >
      <div className="flex shrink-0 border-b">
        {CATEGORIES.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => {
              setCat(c.id);
              setActiveIdx(0);
              setVisibleCount(INIT_VISIBLE);
            }}
            className={cn(
              "px-3 py-1.5 text-xs transition-colors",
              cat === c.id
                ? "border-b-2 border-primary font-medium text-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {c.label}
            <span className="ml-1 text-muted-foreground/70">
              {data[c.id]?.length ?? 0}
            </span>
          </button>
        ))}
        {data.datasources?.map((ds) => {
          const id = "ds:" + ds.name;
          return (
            <button
              key={id}
              type="button"
              onClick={() => {
                setCat(id);
                setActiveIdx(0);
                setVisibleCount(INIT_VISIBLE);
              }}
              className={cn(
                "px-3 py-1.5 text-xs transition-colors",
                cat === id
                  ? "border-b-2 border-teal-500 font-medium text-teal-700"
                  : "text-muted-foreground hover:text-foreground",
              )}
              title={ds.db_type}
            >
              {ds.label}
              <span className="ml-1 text-muted-foreground/70">
                {ds.tables.length}
              </span>
            </button>
          );
        })}
      </div>
      <div className="shrink-0 border-b p-1.5">
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActiveIdx(0);
            setVisibleCount(INIT_VISIBLE);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              setOpen(false);
            } else if (e.key === "ArrowDown") {
              e.preventDefault();
              const ni = Math.min(activeIdx + 1, items.length - 1);
              setActiveIdx(ni);
              setTimeout(
                () =>
                  listRef.current
                    ?.querySelector<HTMLElement>(`[data-idx="${ni}"]`)
                    ?.scrollIntoView({ block: "nearest" }),
                0,
              );
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              const ni = Math.max(activeIdx - 1, 0);
              setActiveIdx(ni);
              setTimeout(
                () =>
                  listRef.current
                    ?.querySelector<HTMLElement>(`[data-idx="${ni}"]`)
                    ?.scrollIntoView({ block: "nearest" }),
                0,
              );
            } else if (e.key === "Enter" && items[activeIdx]) {
              e.preventDefault();
              insertItem(items[activeIdx]);
            }
          }}
          placeholder={"搜索表单..."}
          className="w-full rounded border bg-background px-2 py-1 text-xs outline-none focus:border-primary"
        />
      </div>
      <div
        ref={listRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          if (el.scrollTop + el.clientHeight >= el.scrollHeight - 40) {
            setVisibleCount((c) => c + PAGE_SIZE);
          }
        }}
        className="overflow-y-auto p-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {items.length === 0 ? (
          <div className="p-2 text-xs text-muted-foreground">{"无匹配单据"}</div>
        ) : (
          items.map((it, i) => (
            <button
              key={`${it.id ?? it.table}-${i}`}
              data-idx={i}
              type="button"
              onMouseEnter={() => setActiveIdx(i)}
              onClick={() => insertItem(it)}
              className={cn(
                "flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs",
                i === activeIdx ? "bg-accent" : "hover:bg-accent/50",
              )}
            >
              <span className="font-medium text-foreground">
                {it.chinese_name || it.table}
              </span>
              {it.table ? (
                <span
                  title={it.table}
                  className={cn(
                    "shrink-0 max-w-[200px] truncate rounded border px-1.5 py-0.5 text-[10px] font-medium leading-none",
                    mentionBadgeClass(currentMentionType(), it.table),
                  )}
                >
                  {cat.startsWith("ds:") ? `[${cat.slice(3)}] ${it.table}` : it.table}
                </span>
              ) : null}
              {it.module ? (
                <span className="ml-auto shrink-0 text-muted-foreground/70">
                  [{it.module}]
                </span>
              ) : null}
              {it.row_count != null ? (
                <span className="ml-auto shrink-0 text-muted-foreground/70">
                  {it.row_count} 行
                </span>
              ) : null}
            </button>
          ))
        )}
        {total > items.length ? (
          <div className="p-1 text-center text-[10px] text-muted-foreground/70">
            {"已加载 "}{items.length}{" / "}{total}{"，向下滚动加载更多"}
          </div>
        ) : total > 0 ? (
          <div className="p-1 text-center text-[10px] text-muted-foreground/70">
            {"共 "}{total}{" 张"}
          </div>
        ) : null}
      </div>
    </div>
  );
}
