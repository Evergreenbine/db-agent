"use client";

import { useState, useCallback, useMemo } from "react";
import type { ReactNode } from "react";
import { makeAssistantToolUI } from "@assistant-ui/react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { format as formatSqlRaw } from "sql-formatter";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/lib/auth-store";
import { useSessionStore } from "@/lib/session-store";
import { useComposerBridge } from "@/lib/composer-bridge";
import { SqlBlock } from "./elements/sql-block";
import {
  CheckIcon,
  XIcon,
  CopyIcon,
  CheckCheckIcon,
  DatabaseIcon,
  Loader2Icon,
  AlertTriangleIcon,
  PencilIcon,
  Trash2Icon,
  PlusIcon,
  GitMergeIcon,
} from "lucide-react";

type ColumnMeta = { name: string; table?: string; label?: string; affected?: boolean };
type PreviewData = { columns: string[]; rows: unknown[][]; count?: number; truncated?: boolean };
type WriteStep = {
  action: string; table: string; table_label?: string; sql: string; preview_sql?: string;
  columns?: unknown[]; column_labels?: Record<string, string>; column_meta?: ColumnMeta[];
  description?: string; datasource?: string;
  preview?: PreviewData | { error?: string; detail?: string }; error?: string; detail?: string;
};
type PreviewResult = { requires_confirm?: boolean; step_count?: number; steps?: WriteStep[]; error?: string; detail?: string };

function parseResult(result: unknown): PreviewResult | null {
  if (!result) return null;
  try { const raw = typeof result === "string" ? result : JSON.stringify(result); return JSON.parse(raw) as PreviewResult; } catch { return null; }
}



function datasourceLabel(ds?: string): string {
  const d = (ds || "").trim().toLowerCase();
  if (!d || d === "oa") return "OA · Oracle";
  if (d === "hr") return "HR · G4PRO";
  return ds || "OA";
}

function normalizeColumnList(cols: unknown[] | undefined): Map<string, string | undefined> {
  const map = new Map<string, string | undefined>();
  if (!cols) return map;
  for (const c of cols) {
    if (typeof c === "string") { map.set(c.toLowerCase(), undefined); }
    else if (c && typeof c === "object" && "name" in c) { const o = c as { name: string; table?: string }; map.set((o.name||"").toLowerCase(), o.table); }
  }
  return map;
}

type ColorSet = { dot: string; text: string; thBg: string; cellBg: string };
const AFFECTED: ColorSet = { dot: "bg-red-500", text: "text-red-600", thBg: "bg-red-50 dark:bg-red-950/30", cellBg: "bg-red-50/70 dark:bg-red-950/20" };
const SOURCE_PALETTE: ColorSet[] = [
  { dot: "bg-emerald-500", text: "text-emerald-600", thBg: "bg-emerald-50 dark:bg-emerald-950/30", cellBg: "bg-emerald-50/60 dark:bg-emerald-950/20" },
  { dot: "bg-violet-500", text: "text-violet-600", thBg: "bg-violet-50 dark:bg-violet-950/30", cellBg: "bg-violet-50/60 dark:bg-violet-950/20" },
  { dot: "bg-sky-500", text: "text-sky-600", thBg: "bg-sky-50 dark:bg-sky-950/30", cellBg: "bg-sky-50/60 dark:bg-sky-950/20" },
  { dot: "bg-amber-500", text: "text-amber-600", thBg: "bg-amber-50 dark:bg-amber-950/30", cellBg: "bg-amber-50/60 dark:bg-amber-950/20" },
  { dot: "bg-pink-500", text: "text-pink-600", thBg: "bg-pink-50 dark:bg-pink-950/30", cellBg: "bg-pink-50/60 dark:bg-pink-950/20" },
];
const DEFAULT_COLOR: ColorSet = { dot: "bg-zinc-400", text: "text-zinc-500", thBg: "", cellBg: "" };
type ColInfo = { name: string; label: string; table?: string; tableLabel?: string; affected: boolean; color: ColorSet };

function buildColumnInfos(step: WriteStep): ColInfo[] {
  const pv = step.preview;
  if (!pv || "error" in pv || !(pv as PreviewData).columns) return [];
  const preview = pv as PreviewData;
  const metaMap = new Map<string, ColumnMeta>();
  for (const m of step.column_meta || []) metaMap.set((m.name||"").toLowerCase(), m);
  const affectedCols = normalizeColumnList(step.columns);
  const sourceTables: string[] = [];
  for (const col of preview.columns) {
    const key = (col||"").toLowerCase();
    const meta = metaMap.get(key);
    const isAffected = meta?.affected || affectedCols.has(key);
    if (!isAffected) { const tbl = meta?.table || affectedCols.get(key) || step.table; if (tbl && !sourceTables.includes(tbl)) sourceTables.push(tbl); }
  }
  return preview.columns.map((col) => {
    const key = (col||"").toLowerCase();
    const meta = metaMap.get(key);
    const isAffected = meta?.affected || affectedCols.has(key);
    const tbl = meta?.table || (isAffected ? step.table : undefined);
    let color: ColorSet;
    if (isAffected) color = AFFECTED;
    else if (tbl && sourceTables.includes(tbl)) color = SOURCE_PALETTE[sourceTables.indexOf(tbl) % SOURCE_PALETTE.length];
    else color = DEFAULT_COLOR;
    const label = meta?.label || step.column_labels?.[col] || col;
    const tableLabel = isAffected ? (step.table_label || "主表") : (tbl ? tbl : "");
    return { name: col, label, table: tbl, tableLabel, affected: isAffected, color };
  });
}

const ACTION_CFG: Record<string, { label: string; icon: typeof PencilIcon; badge: string }> = {
  update: { label: "更新", icon: PencilIcon, badge: "text-blue-600 bg-blue-50 dark:bg-blue-950/30" },
  delete: { label: "删除", icon: Trash2Icon, badge: "text-red-600 bg-red-50 dark:bg-red-950/30" },
  insert: { label: "新增", icon: PlusIcon, badge: "text-green-600 bg-green-50 dark:bg-green-950/30" },
  merge: { label: "合并", icon: GitMergeIcon, badge: "text-violet-600 bg-violet-50 dark:bg-violet-950/30" },
};


function StepPreviewTable({ step }: { step: WriteStep }) {
  const colInfos = useMemo(() => buildColumnInfos(step), [step]);
  const pv = step.preview;
  if (!pv || "error" in pv) {
    if (pv && "error" in pv && pv.error)
      return <div className="flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-400"><AlertTriangleIcon className="size-3.5 shrink-0" />预览数据获取失败：{pv.detail || pv.error}</div>;
    return null;
  }
  const preview = pv as PreviewData;
  if (!preview.columns || !preview.rows || preview.rows.length === 0)
    return <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900/50">暂无预览数据</div>;
  const legendItems: { color: ColorSet; label: string }[] = [];
  const seen = new Set<string>();
  for (const ci of colInfos) {
    if (ci.affected && !seen.has("__aff__")) { seen.add("__aff__"); legendItems.push({ color: AFFECTED, label: step.table_label || step.table || "被更新" }); }
    if (!ci.affected && ci.table && !seen.has(ci.table)) { seen.add(ci.table); legendItems.push({ color: ci.color, label: ci.table }); }
  }
  return (
    <div className="space-y-1.5">
      {legendItems.length > 1 && (
        <div className="flex flex-wrap gap-3 px-0.5 text-[10px] text-zinc-400">
          {legendItems.map((item, i) => (<span key={i} className="flex items-center gap-1"><span className={"inline-block size-1.5 rounded-full " + item.color.dot} />{item.label}</span>))}
        </div>
      )}
      <div className="preview-scroll max-h-64 overflow-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
        <table className="w-max border-collapse text-xs">
          <thead className="sticky top-0 z-10"><tr>
            <th className="border-b border-zinc-200 bg-zinc-100 px-2 py-1.5 text-left font-medium text-zinc-400 dark:border-zinc-800 dark:bg-zinc-900">#</th>
            {colInfos.map((ci, i) => (
              <th key={i} className={"whitespace-nowrap border-b border-zinc-200 px-2.5 py-1.5 text-left font-medium dark:border-zinc-800 " + ci.color.thBg}>
                <span className="flex items-center gap-1"><span className={"inline-block size-1.5 rounded-full " + ci.color.dot} /><span className={"font-semibold " + ci.color.text}>{ci.label}</span><span className="text-[10px] font-normal text-zinc-400">{ci.name}</span>{ci.tableLabel && <span className={"text-[10px] font-normal " + ci.color.text}>{ci.tableLabel}</span>}{ci.affected && <span className="text-[10px] text-red-500">✎</span>}</span>
              </th>
            ))}
          </tr></thead>
          <tbody>
            {preview.rows.map((row, ri) => (
              <tr key={ri} className="border-b border-zinc-100 last:border-0 dark:border-zinc-900">
                <td className="px-2 py-1 text-[11px] text-zinc-400">{ri + 1}</td>
                {colInfos.map((ci, ci2) => {
                  const val = row[ci2]; const display = val == null ? "∅" : String(val);
                  if (ci.affected) return <td key={ci2} className={"whitespace-nowrap px-2.5 py-1 " + ci.color.cellBg}><span className="font-semibold text-red-600 line-through dark:text-red-400">{display}</span></td>;
                  if (ci.table) return <td key={ci2} className={"whitespace-nowrap px-2.5 py-1 " + ci.color.cellBg}><span className={"font-medium " + ci.color.text}>{display}</span></td>;
                  return <td key={ci2} className="whitespace-nowrap px-2.5 py-1 text-zinc-600 dark:text-zinc-300">{display}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {preview.truncated && <div className="px-0.5 text-[10px] text-amber-500">结果已截断，仅显示前 {preview.rows.length} 行（共 {preview.count ?? "?"} 行）</div>}
    </div>
  );
}

function StepAfterTable({ after, step }: { after: PreviewData | { error?: string; detail?: string }; step: WriteStep }) {
  const colInfos = useMemo(() => buildColumnInfos(step), [step]);
  const AFTER_AFFECTED: ColorSet = { dot: "bg-green-500", text: "text-green-600", thBg: "bg-green-50 dark:bg-green-950/30", cellBg: "bg-green-50/70 dark:bg-green-950/20" };
  if ("error" in after) {
    return <div className="flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-400"><AlertTriangleIcon className="size-3.5 shrink-0" />执行后回查失败：{after.detail || after.error}</div>;
  }
  const ap = after as PreviewData;
  if (!ap.columns || !ap.rows || ap.rows.length === 0) {
    return <div className="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-xs text-green-700 dark:border-green-900 dark:bg-green-950/30 dark:text-green-400">✓ 执行后回查：0 行（数据已删除或条件不再命中）</div>;
  }
  const colsMatch = colInfos.length === (ap.columns?.length || 0);
  const renderInfos: ColInfo[] = colsMatch ? colInfos : (ap.columns || []).map((c) => ({ name: String(c), label: String(c), affected: false, color: DEFAULT_COLOR }));
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1 px-0.5 text-[11px] font-medium text-green-600"><span>↓ 执行后实际结果</span>{ap.count != null && <span className="text-zinc-400">（{ap.count} 行）</span>}</div>
      <div className="preview-scroll max-h-64 overflow-auto rounded-lg border border-green-200 dark:border-green-900">
        <table className="w-max border-collapse text-xs">
          <thead className="sticky top-0 z-10"><tr>
            <th className="border-b border-green-200 bg-green-50 px-2 py-1.5 text-left font-medium text-green-500 dark:border-green-900 dark:bg-green-950/50">#</th>
            {renderInfos.map((ci, i) => {
              const color = ci.affected ? AFTER_AFFECTED : ci.color;
              return (
                <th key={i} className={"whitespace-nowrap border-b border-green-200 px-2.5 py-1.5 text-left font-medium dark:border-green-900 " + color.thBg}>
                  <span className="flex items-center gap-1"><span className={"inline-block size-1.5 rounded-full " + color.dot} /><span className={"font-semibold " + color.text}>{ci.label}</span><span className="text-[10px] font-normal text-zinc-400">{ci.name}</span></span>
                </th>
              );
            })}
          </tr></thead>
          <tbody>
            {ap.rows.map((row, ri) => (
              <tr key={ri} className="border-b border-green-100 last:border-0 dark:border-green-900">
                <td className="px-2 py-1 text-[11px] text-zinc-400">{ri + 1}</td>
                {renderInfos.map((ci, ci2) => {
                  const val = row[ci2]; const display = val == null ? "∅" : String(val);
                  const color = ci.affected ? AFTER_AFFECTED : ci.color;
                  if (ci.affected) return <td key={ci2} className={"whitespace-nowrap px-2.5 py-1 " + color.cellBg}><span className="font-semibold text-green-600 dark:text-green-400">{display}</span></td>;
                  if (ci.table) return <td key={ci2} className={"whitespace-nowrap px-2.5 py-1 " + color.cellBg}><span className={"font-medium " + color.text}>{display}</span></td>;
                  return <td key={ci2} className="whitespace-nowrap px-2.5 py-1 text-zinc-600 dark:text-zinc-300">{display}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {ap.truncated && <div className="px-0.5 text-[10px] text-amber-500">结果已截断，仅显示前 {ap.rows.length} 行（共 {ap.count ?? "?"} 行）</div>}
    </div>
  );
}

function StepSection({ step, idx, afterPreview }: { step: WriteStep; idx: number; afterPreview?: PreviewData | { error?: string; detail?: string } }) {
  const cfg = ACTION_CFG[step.action] || ACTION_CFG.update;
  const Icon = cfg.icon;
  return (
    <div className="overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-800">
      <div className="flex items-center gap-2 border-b border-zinc-100 bg-zinc-50/80 px-3 py-2 dark:border-zinc-900 dark:bg-zinc-900/40">
        <span className="text-[11px] font-semibold text-zinc-400">#{idx + 1}</span>
        <span className={"flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold " + cfg.badge}><Icon className="size-3" />{cfg.label}</span>
        <span className="text-xs font-medium text-zinc-700 dark:text-zinc-200">{step.table_label || step.table}</span>
        <span className="text-[11px] text-zinc-400">{datasourceLabel(step.datasource)}</span>
        {step.description && <span className="ml-auto max-w-[260px] truncate text-[11px] text-zinc-400" title={step.description}>{step.description}</span>}
      </div>
      <div className="space-y-2 px-3 py-2.5">
        <StepPreviewTable step={step} />
        {afterPreview && <StepAfterTable after={afterPreview} step={step} />}
        <SqlBlock sql={step.sql} />
        {step.description && <div className="rounded-md bg-blue-50/60 px-2.5 py-1.5 text-[11px] leading-relaxed text-blue-700 dark:bg-blue-950/20 dark:text-blue-300">{step.description}</div>}
      </div>
    </div>
  );
}

function buildExecSummary(res: Record<string, unknown>, steps?: WriteStep[]): string {
  const results = (res.results as Array<Record<string, unknown>>) || [];
  const stepCount = res.step_count as number | undefined;
  const okCount = res.ok_count as number | undefined;
  const partial = res.partial_failure as boolean | undefined;
  const totalRows = results.reduce((sum, r) => sum + ((r.rows_affected as number) || 0), 0);
  const transactional = res.transactional ? "（事务包裹，全部提交）" : "";

  const stepLines = results.map((r, i) => {
    const step = steps?.[i];
    const table = step?.table_label || step?.table || "未知表";
    const sql = (step?.sql || "").replace(/\s+/g, " ").substring(0, 300);
    const rows = (r.rows_affected as number) || 0;
    const after = r.after_preview as { count?: number; rows?: unknown[][]; error?: string } | undefined;
    let afterInfo = "";
    if (after && !after.error) {
      const afterCount = after.count ?? (after.rows?.length ?? 0);
      afterInfo = "，执行后回查 " + afterCount + " 行";
    } else if (after?.error) {
      afterInfo = "，回查失败";
    }
    const status = r.error ? "失败：" + (r.detail || r.error) : "成功，影响 " + rows + " 行" + afterInfo;
    return "【步骤" + (i + 1) + "】" + table + "\n  状态：" + status + "\n  SQL：" + sql;
  }).join("\n");

  if (res.error) {
    return "[执行确认] 数据库变更执行失败：" + (res.detail || res.error) + "\n\n" + stepLines + "\n\n请告知用户执行失败并说明原因。";
  }
  if (partial) {
    const failIdx = results.findIndex((r) => r.error);
    return "[执行确认] 数据库变更部分失败：" + okCount + "/" + stepCount + " 步成功，第 " + (failIdx + 1) + " 步失败。共影响 " + totalRows + " 行。\n\n" + stepLines + "\n\n请告知用户部分成功并说明失败原因，然后用 run_sql 查询验证已执行步骤的数据状态，确认幂等性。";
  }
  const verifySqls = (steps || []).map((s) => s.preview_sql).filter(Boolean);
  const verifySection = verifySqls.length > 0
    ? "\n\n请用 run_sql 执行以下验证查询，确认数据已正确变更（幂等性检查）：\n" + verifySqls.join("\n") + "\n\n确认无误后告知用户执行成功。"
    : "\n\n请告知用户执行成功。";
  return "[执行确认] 数据库变更已执行成功" + transactional + "：" + stepCount + " 步全部完成，共影响 " + totalRows + " 行。\n\n" + stepLines + verifySection;
}

export const WriteConfirmCard = makeAssistantToolUI({
  toolName: "execute_write",
  render: ({ args, result, status, addResult, toolCallId }) => {
    const [executing, setExecuting] = useState(false);
    const [execResult, setExecResult] = useState<Record<string, unknown> | null>(null);
    const [cancelled, setCancelled] = useState(false);
    const data = useMemo(() => parseResult(result), [result]);
    const purpose = useMemo(() => { const a = args as Record<string, unknown> | undefined; return (a?.purpose as string) || ""; }, [args]);
    const persistResult = useCallback((patch: Record<string, unknown>) => {
      const sid = useSessionStore.getState().sessionId;
      if (!sid) return;
      const { token, user } = useAuthStore.getState();
      const h: Record<string, string> = { "Content-Type": "application/json" };
      if (token) h.Authorization = "Bearer " + token;
      if (user?.employeeId) h["X-Employee-Id"] = user.employeeId;
      fetch("/api/agent/patch-exec-result", { method: "POST", headers: h, body: JSON.stringify({ session_id: sid, patch }) }).catch(() => {});
    }, []);


    const handleConfirm = useCallback(async () => {
      if (!data?.steps) return;
      setExecuting(true);
      let json: Record<string, unknown> | null = null;
      try {
        const { token, user } = useAuthStore.getState();
        const headers: Record<string, string> = { "Content-Type": "application/json" };
        if (token) headers.Authorization = "Bearer " + token;
        if (user?.employeeId) headers["X-Employee-Id"] = user.employeeId;
        const body = { steps: data.steps.map((s) => ({ sql: s.sql, datasource: s.datasource || "", table: s.table || "", preview_sql: s.preview_sql || "" })) };
        const res = await fetch("/api/agent/confirm-write", { method: "POST", headers, body: JSON.stringify(body) });
        const text = await res.text();
        try { json = JSON.parse(text) as Record<string, unknown>; } catch { json = { error: "PARSE_ERROR", detail: text.substring(0, 200) }; }
        setExecResult(json);
      } catch (e) {
        json = { error: "EXECUTE_FAILED", detail: String(e) };
        setExecResult(json);
      } finally { setExecuting(false); }
      if (json) {
        try {
          addResult?.({ ...data, executed: !json.error, exec_result: json });
          persistResult({ executed: !json.error, exec_result: json });
          const summary = buildExecSummary(json, data.steps);
          const sendMessage = useComposerBridge.getState().sendMessage;
          if (!sendMessage) {
            console.error("[WriteConfirmCard] bridge sendMessage 不可用");
            return;
          }
          sendMessage(summary);
        } catch (e) {
          console.error("[WriteConfirmCard] 通知 agent 执行结果失败:", e);
        }
      }
    }, [data, addResult, persistResult]);

    const handleCancel = useCallback(() => {
      setCancelled(true);
      addResult?.({ ...data, executed: false, user_decision: "cancelled" });
      persistResult({ executed: false, user_decision: "cancelled" });
      try {
        const sendMessage = useComposerBridge.getState().sendMessage;
        if (!sendMessage) {
          console.error("[WriteConfirmCard] bridge sendMessage 不可用");
          return;
        }
        sendMessage("[执行取消] 用户已取消本次数据库变更操作，不执行。请确认用户已取消。");
      } catch (e) {
        console.error("[WriteConfirmCard] 通知 agent 取消操作失败:", e);
      }
    }, [data, addResult, persistResult]);

    if (status.type === "running") return <div className="my-3 flex items-center gap-2 rounded-xl border border-dashed border-muted-foreground/30 p-4 text-sm text-muted-foreground"><Loader2Icon className="size-4 animate-spin" />正在生成数据变更预览...</div>;
    if (!data) return null;
    const hasError = data.error || data.steps?.some((s) => s.error);
    const validSteps = data.steps || [];
    const execR = execResult || (data?.exec_result as Record<string, unknown> | null) || null;
    const execHasErr = !!(execR && execR.error);
    const execPartial = execR ? (execR.partial_failure as boolean | undefined) : false;
    const effectiveCancelled = cancelled || data?.user_decision === "cancelled";
    const execResults = execR ? (execR.results as Array<Record<string, unknown>>) || [] : [];
    const execTotalRows = execResults.reduce((sum, r) => sum + ((r.rows_affected as number) || 0), 0);
    const footerColor = effectiveCancelled ? "text-red-600" : (execHasErr || execPartial) ? "text-amber-600" : execR ? "text-green-600" : "";
    const footerText = effectiveCancelled ? "用户已取消，不执行变更"
      : execHasErr ? "执行失败：" + (execR && (execR.detail || execR.error) || "")
      : execPartial ? "部分成功（" + (execR && execR.ok_count) + "/" + (execR && execR.step_count) + " 步），共影响 " + execTotalRows + " 行"
      : execR ? "已执行（" + (execR && execR.step_count) + " 步全部成功，共影响 " + execTotalRows + " 行）"
      : "";
    return (
      <>
        <style>{"\n          .preview-scroll::-webkit-scrollbar { height: 8px; width: 8px; }\n          .preview-scroll::-webkit-scrollbar-track { background: transparent; }\n          .preview-scroll::-webkit-scrollbar-thumb { background: rgba(161,161,170,0.4); border-radius: 4px; }\n          .preview-scroll::-webkit-scrollbar-thumb:hover { background: rgba(161,161,170,0.6); }\n        "}</style>
        <div className="my-3 overflow-hidden rounded-xl border bg-card shadow-sm dark:border-zinc-800">
          <div className="flex items-center gap-2 border-b bg-muted/50 px-4 py-2.5 dark:border-zinc-800"><DatabaseIcon className="size-4 text-primary" /><span className="text-sm font-semibold">数据变更预览</span>{validSteps.length > 0 && <span className="ml-auto rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-500 dark:bg-zinc-800">{validSteps.length} 步</span>}</div>
          {hasError ? <div className="flex items-center gap-1.5 px-4 py-3 text-sm text-red-600"><AlertTriangleIcon className="size-4 shrink-0" />{data.detail || data.error || "预览生成失败"}</div> : (
            <>
              {purpose && <div className="border-b px-4 py-2 text-xs text-muted-foreground dark:border-zinc-800"><b className="font-medium text-foreground">目的：</b>{purpose}</div>}
              <div className="space-y-2.5 px-4 py-3">{validSteps.map((step, i) => <StepSection key={i} step={step} idx={i} afterPreview={execResults[i]?.after_preview as (PreviewData | { error?: string; detail?: string }) | undefined} />)}</div>
              <div className="flex items-center justify-end gap-2 border-t bg-muted/30 px-4 py-2.5 dark:border-zinc-800">
                {(effectiveCancelled || execR) ? (
                  <span className={"flex items-center gap-1.5 text-sm font-medium " + footerColor}>
                    {effectiveCancelled ? <XIcon className="size-4" /> : (execHasErr || execPartial) ? <AlertTriangleIcon className="size-4" /> : <CheckIcon className="size-4" />}
                    {footerText}
                  </span>
                ) : (
                  <>
                    <Button variant="outline" size="sm" className="h-8" onClick={handleCancel} disabled={executing}><XIcon className="mr-1 size-3.5" />取消</Button>
                    <Button size="sm" className="h-8" onClick={handleConfirm} disabled={executing}>{executing ? <Loader2Icon className="mr-1 size-3.5 animate-spin" /> : <CheckIcon className="mr-1 size-3.5" />}{executing ? "执行中..." : "确定执行 " + validSteps.length + " 步"}</Button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </>
    );
  },
});