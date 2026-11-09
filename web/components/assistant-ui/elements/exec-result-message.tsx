"use client";

import { CheckIcon, XIcon, AlertTriangleIcon, DatabaseIcon } from "lucide-react";
import { SqlBlock } from "./sql-block";

type ExecStatus = "success" | "partial" | "failure" | "cancel";

function parseExecMessage(text: string): { status: ExecStatus; summary: string; steps: { title: string; status: string; sql: string }[]; verifyLabel: string; verifySql: string } | null {
  const isConfirm = text.startsWith("[执行确认]");
  const isCancel = text.startsWith("[执行取消]");
  if (!isConfirm && !isCancel) return null;

  if (isCancel) {
    return { status: "cancel", summary: text.replace("[执行取消] ", ""), steps: [], verifyLabel: "", verifySql: "" };
  }

  // Parse [执行确认] message
  const body = text.replace("[执行确认] ", "");
  const lines = body.split("\n");

  // First line is the summary
  const summary = lines[0] || "";

  // Determine status
  let status: ExecStatus = "success";
  if (summary.includes("失败")) status = "failure";
  else if (summary.includes("部分")) status = "partial";

  // Parse steps
  const steps: { title: string; status: string; sql: string }[] = [];
  let currentStep: { title: string; status: string; sql: string } | null = null;
  let verifyLabel = "";
  let verifySql = "";
  let inVerifySql = false;

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("【步骤")) {
      if (currentStep) steps.push(currentStep);
      currentStep = { title: line, status: "", sql: "" };
      inVerifySql = false;
    } else if (line.startsWith("  状态：") && currentStep) {
      currentStep.status = line.trim();
      inVerifySql = false;
    } else if (line.startsWith("  SQL：") && currentStep) {
      currentStep.sql = line.replace("  SQL：", "").trim();
      inVerifySql = false;
    } else if (line.includes("请用 run_sql")) {
      verifyLabel = line.trim();
      inVerifySql = true;
    } else if (line.includes("请告知用户") || line.includes("确认无误")) {
      verifyLabel = verifyLabel || line.trim();
      inVerifySql = false;
    } else if (inVerifySql && (line.startsWith("SELECT") || line.startsWith("UPDATE") || line.startsWith("DELETE") || line.startsWith("INSERT") || line.startsWith(" ") || line.startsWith("  "))) {
      verifySql += line + "\n";
    }
  }
  if (currentStep) steps.push(currentStep);

  return { status, summary, steps, verifyLabel, verifySql: verifySql.trim() };
}

const STATUS_CFG: Record<ExecStatus, { icon: typeof CheckIcon; color: string; bg: string; border: string; label: string }> = {
  success: { icon: CheckIcon, color: "text-green-600", bg: "bg-green-50 dark:bg-green-950/30", border: "border-green-200 dark:border-green-900", label: "执行成功" },
  partial: { icon: AlertTriangleIcon, color: "text-amber-600", bg: "bg-amber-50 dark:bg-amber-950/30", border: "border-amber-200 dark:border-amber-900", label: "部分成功" },
  failure: { icon: AlertTriangleIcon, color: "text-red-600", bg: "bg-red-50 dark:bg-red-950/30", border: "border-red-200 dark:border-red-900", label: "执行失败" },
  cancel: { icon: XIcon, color: "text-zinc-500", bg: "bg-zinc-50 dark:bg-zinc-900/30", border: "border-zinc-200 dark:border-zinc-800", label: "已取消" },
};

export function ExecResultMessage({ text }: { text: string }) {
  const parsed = parseExecMessage(text);

  if (!parsed) return <>{text}</>;

  const cfg = STATUS_CFG[parsed.status];
  const Icon = cfg.icon;

  return (
    <div className={"exec-result-msg my-1 overflow-hidden rounded-lg border " + cfg.border + " " + cfg.bg}>
      <div className={"flex items-center gap-2 px-3 py-2 " + cfg.color}>
        <Icon className="size-4 shrink-0" />
        <span className="text-sm font-semibold">{cfg.label}</span>
        <span className="ml-auto text-xs font-normal opacity-70">{parsed.summary.replace(/数据库变更已执行成功|数据库变更部分失败|数据库变更执行失败/g, "").trim()}</span>
      </div>
      {parsed.steps.length > 0 && (
        <div className="space-y-1 px-3 py-2">
          {parsed.steps.map((step, i) => (
            <div key={i} className="rounded-md bg-background/60 px-2 py-1.5 text-xs">
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-foreground">{step.title}</span>
              </div>
              {step.status && <div className="mt-0.5 text-muted-foreground">{step.status}</div>}
              {step.sql && (
                <div className="mt-1"><SqlBlock sql={step.sql} compact /></div>
              )}
            </div>
          ))}
        </div>
      )}
      {parsed.verifyLabel && (
        <div className="border-t border-current/10 px-3 py-2 text-xs">
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <DatabaseIcon className="size-3" />
            <span>{parsed.verifyLabel}</span>
          </div>
          {parsed.verifySql && (
            <div className="mt-1"><SqlBlock sql={parsed.verifySql} compact /></div>
          )}
        </div>
      )}
      {!parsed.steps.length && !parsed.verifySql && parsed.summary && (
        <div className="px-3 py-2 text-xs text-muted-foreground">{parsed.summary}</div>
      )}
    </div>
  );
}

export function isExecMessage(text: string): boolean {
  return text.startsWith("[执行确认]") || text.startsWith("[执行取消]");
}
