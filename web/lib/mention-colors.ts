export type MentionType = "workflow" | "modeled" | "builtin" | "datasource";

/** 表名标签配色：建模按 uf_ 区分实体表(蓝)/虚拟表(黄)；流程表单橙(明亮)；系统内置表灰。 */
export function mentionBadgeClass(type: MentionType, table: string): string {
  if (type === "datasource") {
    return "border-teal-300 bg-teal-50 text-teal-700";
  }
  if (type === "modeled") {
    return /^uf_/i.test(table)
      ? "border-blue-300 bg-blue-50 text-blue-700"
      : "border-amber-300 bg-amber-50 text-amber-700";
  }
  if (type === "workflow") {
    return "border-orange-400 bg-orange-100 text-orange-700";
  }
  return "border-zinc-300 bg-zinc-100 text-zinc-600";
}

/** 内联 chip 配色（用 outline 不挤动光标），与 badge 同色板。 */
export function mentionChipClass(type: MentionType, table: string): string {
  if (type === "datasource") {
    return "bg-teal-50 text-teal-700 [outline:1px_solid_var(--color-teal-300)]";
  }
  if (type === "modeled") {
    return /^uf_/i.test(table)
      ? "bg-blue-50 text-blue-700 [outline:1px_solid_var(--color-blue-300)]"
      : "bg-amber-50 text-amber-700 [outline:1px_solid_var(--color-amber-300)]";
  }
  if (type === "workflow") {
    return "bg-orange-100 text-orange-700 [outline:1px_solid_var(--color-orange-400)]";
  }
  return "bg-zinc-100 text-zinc-600 [outline:1px_solid_var(--color-zinc-300)]";
}
