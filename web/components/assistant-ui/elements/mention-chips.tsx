"use client";

import { useState, useRef, useCallback } from "react";
import { useMentionStore, type MentionItem } from "@/lib/mention-store";
import { mentionBadgeClass } from "@/lib/mention-colors";

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

const TYPE_LABEL: Record<MentionItem["type"], string> = {
  workflow: "流程表单",
  modeled: "建模表单",
  builtin: "系统内置表",
  datasource: "数据源表",
};

const keyOf = (m: MentionItem) => `${m.table}|${m.id ?? ""}`;

export function MentionChips() {
  const mentions = useMentionStore((s) => s.mentions);
  const remove = useMentionStore((s) => s.remove);
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const cacheRef = useRef<Record<string, Detail>>({});
  const [loadingKey, setLoadingKey] = useState<string | null>(null);

  const fetchDetail = useCallback(async (m: MentionItem) => {
    const key = keyOf(m);
    if (cacheRef.current[key]) return;
    setLoadingKey(key);
    try {
      const params = new URLSearchParams({ type: m.type, table: m.table });
      if (m.id !== undefined && m.id !== null) params.set("id", String(m.id));
      if (m.datasource) params.set("datasource", m.datasource);
      const res = await fetch(`/api/forms/detail?${params.toString()}`);
      cacheRef.current[key] = (await res.json()) as Detail;
    } catch {
      cacheRef.current[key] = { error: "加载失败" };
    } finally {
      setLoadingKey(null);
    }
  }, []);

  if (mentions.length === 0) return null;

  return (
    <div className="aui-mention-chips flex flex-wrap gap-1.5">
      {mentions.map((m, idx) => {
        const key = keyOf(m);
        const detail = cacheRef.current[key];
        return (
          <span
            key={`${key}-${idx}`}
            className="relative inline-flex"
            onMouseEnter={() => {
              setHoverKey(key);
              fetchDetail(m);
            }}
            onMouseLeave={() => setHoverKey(null)}
          >
            <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium cursor-default ${mentionBadgeClass(m.type, m.table)} hover:opacity-80`}>
              <span className="max-w-[12rem] truncate">{m.label}</span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  remove(idx);
                }}
                className="ml-0.5 rounded-sm px-0.5 leading-none hover:bg-black/10"
                aria-label={`移除 ${m.label}`}
              >
                x
              </button>
            </span>
            {hoverKey === key ? (
              <MentionCard
                loading={loadingKey === key && !detail}
                detail={detail}
                mention={m}
              />
            ) : null}
          </span>
        );
      })}
    </div>
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
  const fields = detail?.main_fields ?? detail?.fields ?? [];
  const fieldRows = fields.slice(0, 12).map((f) => ({
    col: f.field ?? f.name ?? "",
    cn: f.label ?? f.chinese_name ?? "",
    type: f.db_type ?? f.data_type ?? "",
  }));
  return (
    <div className="absolute bottom-full left-0 z-50 w-72 rounded-lg border bg-popover p-2.5 text-xs shadow-lg">
      <div className="font-medium text-foreground">{mention.label}</div>
      <div className="mt-0.5 text-muted-foreground">
        物理表{" "}
        <span className="font-mono text-foreground">
          {detail?.table ?? mention.table}
        </span>
        <span className="ml-2">[{mention.type === "datasource" ? (mention.datasource ?? "数据源") : TYPE_LABEL[mention.type]}]</span>
      </div>
      {detail?.module ? (
        <div className="text-muted-foreground">模块：{detail.module}</div>
      ) : null}
      {loading ? (
        <div className="mt-1.5 text-muted-foreground">加载字段中...</div>
      ) : detail?.error ? (
        <div className="mt-1.5 text-destructive">{detail.error}</div>
      ) : fieldRows.length > 0 ? (
        <div className="mt-1.5 max-h-48 overflow-y-auto">
          <div className="mb-0.5 text-muted-foreground">
            字段（前 {fieldRows.length}）：
          </div>
          <div className="space-y-0.5">
            {fieldRows.map((r, i) => (
              <div key={i} className="flex gap-1.5">
                <span className="shrink-0 font-mono text-foreground">{r.col}</span>
                <span className="truncate text-muted-foreground">{r.cn}</span>
                {r.type ? (
                  <span className="ml-auto shrink-0 text-muted-foreground/70">
                    {r.type}
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {detail?.detail_tables && detail.detail_tables.length > 0 ? (
        <div className="mt-1.5 text-muted-foreground">
          明细表：
          {detail.detail_tables.map((d) => d.detail_table).join(", ")}
        </div>
      ) : null}
    </div>
  );
}
