"use client";

import { useMemo, useState, useCallback } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { format as formatSqlRaw } from "sql-formatter";
import { CopyIcon, CheckCheckIcon } from "lucide-react";

export function tryFormatSql(sql: string): string {
  if (!sql) return "";
  try { return formatSqlRaw(sql, { language: "plsql", keywordCase: "upper" }); }
  catch { try { return formatSqlRaw(sql, { keywordCase: "upper" }); } catch { return sql; } }
}

export function SqlBlock({ sql, compact }: { sql: string; compact?: boolean }) {
  const formatted = useMemo(() => tryFormatSql(sql), [sql]);
  const [copied, setCopied] = useState(false);
  const onCopy = useCallback(async () => {
    try { await navigator.clipboard.writeText(sql); setCopied(true); window.setTimeout(() => setCopied(false), 2000); } catch {}
  }, [sql]);
  return (
    <div className="overflow-hidden rounded-lg border border-zinc-700/50 bg-[#282c34]">
      <div className="flex items-center justify-between border-b border-zinc-700/50 px-3 py-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">SQL</span>
        <button onClick={onCopy} className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-zinc-400 transition-colors hover:bg-zinc-700/50 hover:text-zinc-200">
          {copied ? <CheckCheckIcon className="size-3.5 text-emerald-400" /> : <CopyIcon className="size-3.5" />}
          {copied ? "已复制" : "复制"}
        </button>
      </div>
      <SyntaxHighlighter language="sql" style={oneDark} PreTag="div"
        customStyle={{ margin: 0, padding: compact ? "8px 12px" : "12px 14px", fontSize: compact ? "11px" : "12.5px", lineHeight: 1.65, background: "transparent" }}
        codeTagProps={{ style: { fontFamily: 'Cascadia Code, JetBrains Mono, Consolas, monospace' } }}
        wrapLongLines>
        {formatted}
      </SyntaxHighlighter>
    </div>
  );
}
