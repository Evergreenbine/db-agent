export interface EncodedMention {
  table: string;
  type: "workflow" | "modeled" | "builtin" | "datasource";
  id?: number;
  label: string;
  detail_table?: string;
  datasource?: string;
}

const MARKER = "@@MENTIONS@@";
const END = "@@END@@";

/** 把 @引用的表单元数据以不可见后缀附在消息文本末尾，供发送后消息渲染时还原成标签。 */
export function encodeMentionsSuffix(
  text: string,
  mentions: EncodedMention[],
): string {
  if (!mentions || mentions.length === 0) return text;
  try {
    return text + "\n" + MARKER + JSON.stringify(mentions) + END;
  } catch {
    return text;
  }
}

/** 从消息文本里剥离后缀，还原 { 干净文本, mentions }。 */
export function decodeMentionsSuffix(text: string): {
  text: string;
  mentions: EncodedMention[];
} {
  if (!text) return { text: "", mentions: [] };
  const idx = text.indexOf(MARKER);
  if (idx < 0) return { text, mentions: [] };
  const start = idx + MARKER.length;
  const endIdx = text.indexOf(END, start);
  if (endIdx < 0) return { text, mentions: [] };
  const json = text.slice(start, endIdx);
  let mentions: EncodedMention[] = [];
  try {
    mentions = JSON.parse(json) as EncodedMention[];
  } catch {
    mentions = [];
  }
  let clean = text.slice(0, idx);
  if (clean.endsWith("\n")) clean = clean.slice(0, -1);
  return { text: clean, mentions };
}
