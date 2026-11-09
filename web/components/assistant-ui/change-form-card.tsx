"use client";

import { useState } from "react";
import { makeAssistantToolUI, useAui } from "@assistant-ui/react";
import { Button } from "@/components/ui/button";
import { CheckIcon, XIcon, FileEditIcon, ArrowRightIcon } from "lucide-react";

type ChangeDetail = {
  change_id: string;
  request_id: string;
  applicant_id: string;
  target_name: string;
  target_workcode: string;
  changes: Array<{
    field: string;
    old_value: string;
    new_value: string;
  }>;
  summary: string;
  status: string;
};

function parseResult(result: unknown): ChangeDetail | null {
  if (!result) return null;
  try {
    const raw = typeof result === "string" ? result : JSON.stringify(result);
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export const ChangeFormCard = makeAssistantToolUI({
  toolName: "preview_change",
  render: ({ args, result, status, addResult }) => {
    const [decision, setDecision] = useState<"none" | "confirmed" | "rejected">("none");
    const aui = useAui();
    const data = parseResult(result);

    if (status.type === "running") {
      return (
        <div className="my-3 flex items-center gap-2 rounded-xl border border-dashed border-muted-foreground/30 p-4 text-sm text-muted-foreground">
          <FileEditIcon className="size-4 animate-pulse" />
          正在生成变更明细...
        </div>
      );
    }

    if (!data) return null;

    if (decision === "confirmed" || decision === "rejected") {
      return (
        <div
          className={`my-3 rounded-xl border p-4 ${
            decision === "confirmed"
              ? "border-green-500/40 bg-green-50 dark:bg-green-950/20"
              : "border-red-500/40 bg-red-50 dark:bg-red-950/20"
          }`}
        >
          <div className="flex items-center gap-2">
            {decision === "confirmed" ? (
              <CheckIcon className="size-4 text-green-600" />
            ) : (
              <XIcon className="size-4 text-red-600" />
            )}
            <span className="text-sm font-medium">
              {decision === "confirmed" ? "已确认，正在执行变更..." : "已拒绝变更"}
            </span>
          </div>
        </div>
      );
    }

    const handleConfirm = () => {
      setDecision("confirmed");
      addResult?.({ ...data, user_decision: "confirmed" });

      window.parent.postMessage({
        type: "oa_agent_action",
        action: "apply_change",
        data: {
          change_id: data.change_id,
          request_id: data.request_id,
          target_name: data.target_name,
          target_workcode: data.target_workcode,
          changes: data.changes,
        }
      }, "*");

      aui.optional.composer?.setText(`确认变更 ${data.change_id}，单据 ${data.request_id}，字段 ${data.changes[0]?.field}，新值 ${data.changes[0]?.new_value}`);
      aui.optional.composer?.send();
    };

    const handleReject = () => {
      setDecision("rejected");
      addResult?.({ ...data, user_decision: "rejected" });
      window.parent.postMessage({
        type: "oa_agent_action",
        action: "reject_change",
        data: { change_id: data.change_id }
      }, "*");
      aui.optional.composer?.setText(`拒绝变更 ${data.change_id}`);
      aui.optional.composer?.send();
    };

    return (
      <div className="my-3 overflow-hidden rounded-xl border bg-card shadow-sm">
        <div className="flex items-center gap-2 border-b bg-muted/50 px-4 py-2.5">
          <FileEditIcon className="size-4 text-primary" />
          <span className="text-sm font-semibold">变更明细确认</span>
          <span className="ml-auto rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-400">
            待确认
          </span>
        </div>

        <div className="space-y-3 px-4 py-3">
          <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
            <span>单据ID: <b className="text-foreground">{data.request_id}</b></span>
            {data.target_name && (
              <span>修改人员: <b className="text-foreground">{data.target_name}</b></span>
            )}
            {data.target_workcode && (
              <span>工号: <b className="text-foreground">{data.target_workcode}</b></span>
            )}
            <span>变更ID: <code className="text-foreground">{data.change_id}</code></span>
          </div>

          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/30 text-xs text-muted-foreground">
                  <th className="px-3 py-1.5 text-left font-medium">字段</th>
                  <th className="px-3 py-1.5 text-left font-medium">原值</th>
                  <th className="px-3 py-1.5 text-center font-medium"></th>
                  <th className="px-3 py-1.5 text-left font-medium">新值</th>
                </tr>
              </thead>
              <tbody>
                {data.changes.map((c, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="px-3 py-2 font-medium">{c.field}</td>
                    <td className="px-3 py-2 text-muted-foreground line-through">{c.old_value}</td>
                    <td className="px-3 py-2 text-center">
                      <ArrowRightIcon className="mx-auto size-3.5 text-muted-foreground" />
                    </td>
                    <td className="px-3 py-2 font-semibold text-primary">{c.new_value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-xs text-muted-foreground">{data.summary}</p>
        </div>

        <div className="flex justify-end gap-2 border-t bg-muted/30 px-4 py-2.5">
          <Button variant="outline" size="sm" className="h-8" onClick={handleReject}>
            <XIcon className="mr-1 size-3.5" />
            拒绝
          </Button>
          <Button size="sm" className="h-8" onClick={handleConfirm}>
            <CheckIcon className="mr-1 size-3.5" />
            确认执行
          </Button>
        </div>
      </div>
    );
  },
});
